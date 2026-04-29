import re

from .validate import amount_positive, date_in_range, inn_checksum_ok


_KPP_LEN = 9


def _w(field: str, code: str, value) -> dict:
    return {"field": field, "code": code, "value": value, "severity": "warning"}


def _date_in_text(iso_date: str, text: str) -> bool:
    try:
        y_s, m_s, d_s = iso_date.split("-")
        y, m, d = int(y_s), int(m_s), int(d_s)
    except (ValueError, AttributeError):
        return False
    yy = y % 100
    candidates = (
        f"{y:04d}-{m:02d}-{d:02d}",
        f"{d:02d}.{m:02d}.{y:04d}",
        f"{d:02d}-{m:02d}-{y:04d}",
        f"{d:02d}/{m:02d}/{y:04d}",
        f"{d}.{m}.{y}",
        f"{d:02d}.{m:02d}.{yy:02d}",
    )
    return any(c in text for c in candidates)


def _amount_in_text(amount: str, text: str) -> bool:
    int_part = amount.split(".")[0].split(",")[0].lstrip("-")
    if not int_part.isdigit() or len(int_part) < 3:
        return True
    pattern = r"\b" + r"\s*".join(re.escape(c) for c in int_part) + r"\b"
    return bool(re.search(pattern, text))


def reconcile(text: str, candidates: dict, llm_output: dict) -> tuple[dict, list[dict]]:
    warnings: list[dict] = []

    for cp in llm_output.get("counterparties") or []:
        if not isinstance(cp, dict):
            continue
        inn = cp.get("inn")
        if inn:
            if not inn_checksum_ok(inn):
                warnings.append(_w("inn", "checksum_failed", inn))
            elif inn not in text:
                warnings.append(_w("inn", "hallucinated", inn))
        kpp = cp.get("kpp")
        if kpp:
            if len(kpp) != _KPP_LEN:
                warnings.append(_w("kpp", "format_invalid", kpp))
            elif kpp not in text:
                warnings.append(_w("kpp", "hallucinated", kpp))

    for d in llm_output.get("dates") or []:
        if not isinstance(d, dict):
            continue
        v = d.get("value")
        if not v:
            continue
        if not date_in_range(v):
            warnings.append(_w("date", "out_of_range_or_format", v))
        elif not _date_in_text(v, text):
            warnings.append(_w("date", "hallucinated", v))

    for a in llm_output.get("amounts") or []:
        if not isinstance(a, dict):
            continue
        v = a.get("value")
        if not v:
            continue
        if not amount_positive(v):
            warnings.append(_w("amount", "non_positive_or_format", v))
        elif not _amount_in_text(v, text):
            warnings.append(_w("amount", "hallucinated", v))

    n = llm_output.get("doc_number")
    if isinstance(n, str) and n.strip() and n not in text:
        warnings.append(_w("doc_number", "hallucinated", n))

    return llm_output, warnings
