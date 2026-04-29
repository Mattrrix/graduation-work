"""LLM bench: прогоняет backend'ы на синтетике + реальных PDF, выдаёт markdown-отчёт.

Для реальных PDF ожидается sidecar `<name>.gt.json` с полями
{doc_type, doc_number, doc_date, amount_total, primary_inn, primary_kpp, primary_name, all_inns};
без него файл прогоняется без скоринга (только latency + JSON выхлоп).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# transform и extract оба используют пакет `app`, поэтому extract-парсеры грузим через importlib.
sys.path.insert(0, str(ROOT / "services" / "transform"))
sys.path.insert(0, str(ROOT / "tools" / "generator"))
os.chdir(ROOT)

import importlib.util  # noqa: E402
import warnings  # noqa: E402

warnings.filterwarnings("ignore", message=".*verify=False.*")
warnings.filterwarnings("ignore", category=Warning, module="urllib3")


def _load_module_from(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_parsers_dir = ROOT / "services" / "extract" / "app" / "parsers"
pdf_parser = _load_module_from("bench_pdf_parser", _parsers_dir / "pdf.py")
docx_parser = _load_module_from("bench_docx_parser", _parsers_dir / "docx.py")
xlsx_parser = _load_module_from("bench_xlsx_parser", _parsers_dir / "xlsx.py")
csv_parser = _load_module_from("bench_csv_parser", _parsers_dir / "csv.py")
txt_parser = _load_module_from("bench_txt_parser", _parsers_dir / "txt.py")

from app.clients import gigachat, mlx_local  # noqa: E402  (services/transform)
from generator.docs import GENERATORS  # noqa: E402  (tools/generator)
from generator.writers import pdf_writer  # noqa: E402

DOC_TYPES = ["invoice", "act", "contract", "waybill", "upd", "payment_order"]

PARSERS = {
    ".pdf": pdf_parser.parse,
    ".docx": docx_parser.parse,
    ".xlsx": xlsx_parser.parse,
    ".csv": csv_parser.parse,
    ".txt": txt_parser.parse,
}


def generate_corpus(out_dir: Path, count_per_type: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for doc_type in DOC_TYPES:
        for i in range(count_per_type):
            doc = GENERATORS[doc_type](rng, parties=2, edge_cases=set())
            filename = f"{doc_type}-bench-{i:03d}.pdf"
            path = out_dir / filename
            pdf_writer.write(doc, path)
            items.append({"path": path, "doc": doc, "filename": filename, "source": "synthetic"})
    return items


def load_real(real_dir: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(real_dir.glob("*")):
        if path.suffix.lower() not in PARSERS:
            continue
        if path.name.endswith(".gt.json"):
            continue
        gt_path = path.with_name(path.name + ".gt.json")
        ground_truth = None
        if gt_path.exists():
            ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
        items.append({
            "path": path,
            "filename": path.name,
            "source": "real",
            "ground_truth": ground_truth,
        })
    return items


def extract_text(path: Path) -> str:
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        return ""
    content = path.read_bytes()
    try:
        result = parser(content, path.name)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] parse failed for {path.name}: {type(e).__name__}: {e}", flush=True)
        return ""
    return result.get("text", "") or ""


async def call_backend(backend: str, text: str, filename: str) -> dict:
    started = time.perf_counter()
    try:
        if backend == "mlx":
            output = await mlx_local.extract(text, filename)
        elif backend == "gigachat":
            output = await gigachat.extract(text, filename)
        elif backend.startswith("gigachat:"):
            _, model = backend.split(":", 1)
            output = await gigachat.extract(text, filename, model_override=model)
        else:
            raise ValueError(f"unknown backend {backend!r}")
        elapsed = time.perf_counter() - started
        return {"ok": True, "latency_s": round(elapsed, 3), "output": output}
    except Exception as e:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        return {"ok": False, "latency_s": round(elapsed, 3), "error": f"{type(e).__name__}: {e}"[:300]}


def gt_from_doc(doc: dict) -> dict:
    parties = doc.get("parties") or []
    primary = parties[0] if parties else None
    primary_inn = primary["inn"] if primary else None
    primary_kpp = (primary.get("kpp") if primary and not primary.get("is_individual") else None)
    return {
        "doc_type": doc["doc_type"],
        "doc_number": doc.get("number"),
        "doc_date": doc["date"].isoformat() if isinstance(doc.get("date"), date) else None,
        "amount_total": str(doc.get("total")) if doc.get("total") is not None else None,
        "primary_inn": primary_inn,
        "primary_kpp": primary_kpp,
        "primary_name": primary["name"] if primary else None,
        "all_inns": sorted({p["inn"] for p in parties if p.get("inn")}),
    }


def predict_from_llm(output: dict) -> dict:
    cps = output.get("counterparties") or []
    primary = next((c for c in cps if isinstance(c, dict) and c.get("is_primary")), None)
    if not primary and cps:
        primary = cps[0] if isinstance(cps[0], dict) else None

    dates = [d for d in (output.get("dates") or []) if isinstance(d, dict) and d.get("value")]
    primary_date = next((d["value"] for d in dates if d.get("role") == "doc_date"), None)
    if not primary_date and dates:
        primary_date = dates[0]["value"]

    amounts = [a for a in (output.get("amounts") or []) if isinstance(a, dict) and a.get("value")]
    total_amount = next((a["value"] for a in amounts if a.get("role") == "total"), None)
    if not total_amount and amounts:
        total_amount = amounts[0]["value"]

    return {
        "doc_type": output.get("doc_type"),
        "doc_number": output.get("doc_number"),
        "doc_date": primary_date,
        "amount_total": total_amount,
        "primary_inn": primary.get("inn") if primary else None,
        "primary_kpp": primary.get("kpp") if primary else None,
        "primary_name": primary.get("name") if primary else None,
        "all_inns": sorted({c["inn"] for c in cps if isinstance(c, dict) and c.get("inn")}),
    }


def normalize_amount(v) -> str | None:
    if v is None or v == "":
        return None
    try:
        return str(Decimal(str(v).replace(",", ".").replace(" ", "")).quantize(Decimal("0.01")))
    except Exception:  # noqa: BLE001
        return None


def field_match(field: str, gt, pred) -> bool:
    if gt is None and pred is None:
        return True
    if gt is None or pred is None:
        return False
    if field == "amount_total":
        return normalize_amount(gt) == normalize_amount(pred)
    if field == "doc_number":
        return str(gt).strip().lower() == str(pred).strip().lower()
    if field == "primary_name":
        gt_tokens = [t for t in str(gt).lower().split() if len(t) > 3]
        pred_l = str(pred).lower()
        return any(t in pred_l for t in gt_tokens) if gt_tokens else str(gt).lower() in pred_l
    if field == "all_inns":
        return set(gt or []) == set(pred or [])
    return str(gt).strip() == str(pred).strip()


FIELDS = ["doc_type", "doc_number", "doc_date", "amount_total",
         "primary_inn", "primary_kpp", "primary_name", "all_inns"]


def score_one(gt: dict, pred: dict) -> dict:
    return {f: field_match(f, gt.get(f), pred.get(f)) for f in FIELDS}


async def run_bench(items: list[dict], backends: list[str]) -> list[dict]:
    results: list[dict] = []
    total = len(items) * len(backends)
    done = 0
    for item in items:
        text = extract_text(item["path"])
        if not text:
            print(f"  [skip] {item['filename']} — empty text after parse", flush=True)
            continue
        gt = item.get("ground_truth")
        if gt is None and "doc" in item:
            gt = gt_from_doc(item["doc"])
        for backend in backends:
            result = await call_backend(backend, text, item["filename"])
            done += 1
            status = "ok" if result["ok"] else "FAIL"
            print(f"  [{done:3d}/{total}] {backend:10s} {item['filename']:42s} "
                  f"{status:>4s} {result['latency_s']:6.2f}s", flush=True)
            entry = {
                "filename": item["filename"],
                "source": item.get("source"),
                "doc_type_gt": gt.get("doc_type") if gt else None,
                "backend": backend,
                "ok": result["ok"],
                "latency_s": result["latency_s"],
                "ground_truth": gt,
            }
            if result["ok"]:
                pred = predict_from_llm(result["output"])
                entry["prediction"] = pred
                entry["match"] = score_one(gt, pred) if gt else None
                entry["raw_output"] = result["output"]
            else:
                entry["error"] = result["error"]
            results.append(entry)
    return results


def latency_stats(times: list[float]) -> dict:
    if not times:
        return {"n": 0, "mean": 0, "median": 0, "p95": 0, "min": 0, "max": 0}
    s = sorted(times)
    n = len(s)
    return {
        "n": n,
        "mean": round(statistics.mean(s), 2),
        "median": round(s[n // 2], 2),
        "p95": round(s[max(0, int(round(n * 0.95)) - 1)], 2),
        "min": round(s[0], 2),
        "max": round(s[-1], 2),
    }


def aggregate(results: list[dict]) -> dict:
    by_backend: dict[str, list[dict]] = {}
    for r in results:
        by_backend.setdefault(r["backend"], []).append(r)

    summary: dict[str, dict] = {}
    for backend, rs in by_backend.items():
        ok_results = [r for r in rs if r["ok"]]
        latencies_ok = [r["latency_s"] for r in ok_results]
        n_total = len(rs)
        n_ok = len(ok_results)

        with_match = [r for r in ok_results if r.get("match") is not None]
        field_scores: dict[str, list[int]] = {f: [] for f in FIELDS}
        for r in with_match:
            for f, ok in r["match"].items():
                field_scores[f].append(1 if ok else 0)
        field_accuracy = {
            f: (round(sum(v) / len(v), 3) if v else None)
            for f, v in field_scores.items()
        }

        type_breakdown: dict[str, dict] = {}
        for r in with_match:
            dt = r["ground_truth"]["doc_type"]
            tb = type_breakdown.setdefault(dt, {"correct": 0, "total": 0})
            tb["total"] += 1
            if r["match"].get("doc_type"):
                tb["correct"] += 1

        summary[backend] = {
            "n_total": n_total,
            "n_ok": n_ok,
            "n_failed": n_total - n_ok,
            "latency_ok": latency_stats(latencies_ok),
            "field_accuracy": field_accuracy,
            "type_breakdown": type_breakdown,
            "n_scored": len(with_match),
        }
    return summary


FIELD_LABELS_RU = {
    "doc_type": "Тип",
    "doc_number": "Номер",
    "doc_date": "Дата",
    "amount_total": "Сумма",
    "primary_inn": "ИНН (primary)",
    "primary_kpp": "КПП (primary)",
    "primary_name": "Имя (primary)",
    "all_inns": "Все ИНН",
}


def render_markdown(summary: dict, total_docs: int, generated_at: str) -> str:
    lines: list[str] = []
    lines.append("# LLM Benchmark — Phase 8\n")
    lines.append(f"_Сгенерировано: {generated_at}_\n")
    lines.append(f"**Документов в прогоне:** {total_docs}\n")
    lines.append(f"**Backend'ы:** {', '.join('`' + b + '`' for b in summary.keys())}\n")

    lines.append("\n## Latency (только успешные вызовы, секунды)\n")
    lines.append("| Backend | n | mean | median | p95 | min | max |")
    lines.append("|---|---|---|---|---|---|---|")
    for b, s in summary.items():
        lat = s["latency_ok"]
        lines.append(f"| `{b}` | {lat['n']} | {lat['mean']} | {lat['median']} | "
                     f"{lat['p95']} | {lat['min']} | {lat['max']} |")

    lines.append("\n## Reliability\n")
    lines.append("| Backend | Total | OK | Failed | Failure % |")
    lines.append("|---|---|---|---|---|")
    for b, s in summary.items():
        rate = (s["n_failed"] / s["n_total"] * 100) if s["n_total"] else 0
        lines.append(f"| `{b}` | {s['n_total']} | {s['n_ok']} | {s['n_failed']} | {rate:.1f}% |")

    lines.append("\n## Field-level accuracy (на документах с ground-truth)\n")
    lines.append("| Поле | " + " | ".join(f"`{b}`" for b in summary.keys()) + " |")
    lines.append("|---|" + "|".join(["---"] * len(summary)) + "|")
    for f in FIELDS:
        row = f"| {FIELD_LABELS_RU[f]} |"
        for b, s in summary.items():
            acc = s["field_accuracy"].get(f)
            row += f" {acc * 100:.0f}% |" if acc is not None else " — |"
        lines.append(row)

    lines.append("\n## Точность классификации по типам документов\n")
    all_types = sorted({t for s in summary.values() for t in s["type_breakdown"].keys()})
    if all_types:
        lines.append("| Тип | " + " | ".join(f"`{b}`" for b in summary.keys()) + " |")
        lines.append("|---|" + "|".join(["---"] * len(summary)) + "|")
        for t in all_types:
            row = f"| {t} |"
            for b, s in summary.items():
                tb = s["type_breakdown"].get(t)
                row += f" {tb['correct']}/{tb['total']} |" if tb and tb["total"] else " — |"
            lines.append(row)
    else:
        lines.append("_Нет документов с ground-truth для скоринга._")

    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description="LLM bench: synth + real → markdown report")
    p.add_argument("--count", type=int, default=2, help="docs per type to generate (0 = skip)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--backends", default="mlx,gigachat", help="comma-separated: mlx, gigachat")
    p.add_argument("--real-dir", type=Path, default=ROOT / "samples" / "real")
    p.add_argument("--out-dir", type=Path, default=ROOT / "tools" / "llm_bench" / "out")
    p.add_argument("--report", type=Path, default=ROOT / "tools" / "llm_bench" / "out" / "report.md")
    args = p.parse_args()

    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    items: list[dict] = []
    if args.count > 0:
        synth_dir = args.out_dir / "synth"
        n_total = args.count * len(DOC_TYPES)
        print(f"=> Generating {args.count}×{len(DOC_TYPES)} = {n_total} synthetic docs in {synth_dir}")
        items.extend(generate_corpus(synth_dir, args.count, seed=args.seed))

    if args.real_dir and args.real_dir.exists():
        real = load_real(args.real_dir)
        if real:
            print(f"=> Loaded {len(real)} real document(s) from {args.real_dir}")
            items.extend(real)

    if not items:
        print("(!) No documents to process. Use --count > 0 or place files in samples/real/.")
        sys.exit(1)

    print(f"=> Running {len(backends)} backend(s) on {len(items)} document(s) "
          f"= {len(items) * len(backends)} LLM calls")
    started = time.perf_counter()
    results = asyncio.run(run_bench(items, backends))
    wall = time.perf_counter() - started
    print(f"=> Done in {wall:.1f}s wall-time")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.out_dir / "results.json"
    raw_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    summary = aggregate(results)
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = render_markdown(summary, total_docs=len(items),
                         generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(md, encoding="utf-8")

    print(f"\nRaw results: {raw_path}")
    print(f"Summary:     {summary_path}")
    print(f"Report:      {args.report}\n")
    print(md)


if __name__ == "__main__":
    main()
