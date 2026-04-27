from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

from . import (
    DOC_TYPES,
    EDGE_CASES,
    FORMATS,
    IP_MODE_DEFAULT,
    IP_MODES,
    MISSING_MODE_DEFAULT,
    MISSING_MODES,
    PARTIES_HARD_CAP,
)
from .docs import GENERATORS, SUPPORTED_FORMATS
from .junk import write_junk
from .writers import csv_writer, docx_writer, pdf_writer, xlsx_writer

logger = logging.getLogger("generator")

WRITERS = {
    "pdf": pdf_writer.write,
    "docx": docx_writer.write,
    "xlsx": xlsx_writer.write,
    "csv": csv_writer.write,
}


def _filename(doc: dict, fmt: str, idx: int) -> str:
    return f"{doc['doc_type']}-{doc['date'].strftime('%Y%m%d')}-{idx:03d}.{fmt}"


def generate_one(
    doc_type: str,
    fmt: str,
    out_dir: Path,
    idx: int,
    rng: random.Random,
    *,
    parties: int = 2,
    edge_cases: set[str] | None = None,
    ip_mode: str = IP_MODE_DEFAULT,
    missing_mode: str = MISSING_MODE_DEFAULT,
) -> Path | None:
    if fmt not in SUPPORTED_FORMATS[doc_type]:
        logger.warning("skip %s/%s: format not supported by template", doc_type, fmt)
        return None
    doc = GENERATORS[doc_type](
        rng, parties=parties, edge_cases=edge_cases or set(),
        ip_mode=ip_mode, missing_mode=missing_mode,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / _filename(doc, fmt, idx)
    WRITERS[fmt](doc, path)
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="generator", description="Synthetic document generator")
    p.add_argument("--type", action="append", choices=DOC_TYPES,
                   help="Document type (repeatable). Default: all MVP types (invoice, act, contract).")
    p.add_argument("--format", action="append", choices=FORMATS,
                   help="Output format (repeatable). Default: all formats supported by each type.")
    p.add_argument("--count", type=int, default=5, help="Documents per (type, format) combination. Default: 5.")
    p.add_argument("--out", type=Path, default=Path("./out"), help="Output directory. Default: ./out")
    p.add_argument("--seed", type=int, default=None, help="Random seed for deterministic output (F-G4).")
    p.add_argument("--include-junk", type=int, default=0, metavar="N",
                   help="Also generate N negative documents (F-G5: empty, garbled, irrelevant text).")
    p.add_argument("--parties", type=int, default=2,
                   help=f"Counterparties per document (2..{PARTIES_HARD_CAP}); silently capped per doc-type.")
    p.add_argument("--edge-case", action="append", choices=EDGE_CASES, default=[],
                   help=f"Edge case to inject (repeatable): {', '.join(EDGE_CASES)}.")
    p.add_argument("--ip-mode", choices=IP_MODES, default=IP_MODE_DEFAULT,
                   help="IP intensity (when --edge-case ip_forms): random ~35%%, guaranteed ≥1, all = все стороны ИП.")
    p.add_argument("--missing-mode", choices=MISSING_MODES, default=MISSING_MODE_DEFAULT,
                   help="Missing-fields intensity (when --edge-case missing_optional): random ~20/15%%, guaranteed ≥1 ЛЕ без КПП и города, all = все ЛЕ без КПП и города.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    rng = random.Random(args.seed)
    types = args.type or ["invoice", "act", "contract"]
    formats = args.format or list(FORMATS)
    parties = max(2, min(int(args.parties), PARTIES_HARD_CAP))
    edge_cases = set(args.edge_case)

    args.out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for doc_type in types:
        for fmt in formats:
            if fmt not in SUPPORTED_FORMATS[doc_type]:
                continue
            for i in range(1, args.count + 1):
                path = generate_one(
                    doc_type, fmt, args.out / doc_type, i, rng,
                    parties=parties, edge_cases=edge_cases,
                    ip_mode=args.ip_mode, missing_mode=args.missing_mode,
                )
                if path is not None:
                    written.append(path)
                    logger.info("wrote %s", path)

    if args.include_junk:
        junk_paths = write_junk(args.out / "junk", args.include_junk, rng)
        written.extend(junk_paths)
        for p in junk_paths:
            logger.info("wrote (junk) %s", p)

    logger.info("done: %d files in %s", len(written), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
