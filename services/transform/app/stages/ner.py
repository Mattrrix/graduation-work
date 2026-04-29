import re
from datetime import date
from decimal import Decimal, InvalidOperation

INN_RE       = re.compile(r"\b(\d{10}|\d{12})\b")
KPP_RE       = re.compile(r"\b(\d{4}[A-Z\d]{2}\d{3})\b")
NUMBER_RE    = re.compile(r"(?:№|N\.?|номер)\s*([A-ZА-Я0-9][A-ZА-Я0-9\-_/]+)", re.I)
DATE_RE      = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
AMOUNT_RE    = re.compile(r"(?:итого|всего|сумма|к\s+оплате)[^\d\n%]{0,30}(\d[\d ]{2,15}(?:[.,]\d{1,2})?)(?!\s*%)", re.I)
VAT_RATE_RE  = re.compile(r"НДС[\s:]{0,5}(\d{1,2}(?:[.,]\d{1,2})?)\s*%", re.I)
COUNTERPARTY_RE = re.compile(r"\b(ООО|ОАО|ЗАО|ИП|ПАО|АО)\s+[«\"']?([^«\"'\n,;()]+)[»\"']?", re.I)


def _to_iso(d1: str, d2: str, d3: str, alt: tuple[str, str, str] | None) -> str | None:
    try:
        if alt and alt[0]:
            y, m, d = int(alt[0]), int(alt[1]), int(alt[2])
        else:
            day, month, year = int(d1), int(d2), int(d3)
            if year < 100:
                year += 2000
            d, m, y = day, month, year
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return None


def _parse_amount(s: str) -> str | None:
    cleaned = s.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def _dedup(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def find_candidates(text: str) -> dict:
    inns = _dedup(INN_RE.findall(text))
    kpps = _dedup(KPP_RE.findall(text))

    numbers: list[str] = []
    for m in NUMBER_RE.finditer(text):
        candidate = m.group(1).strip()
        if any(c.isdigit() for c in candidate) and candidate not in numbers:
            numbers.append(candidate)

    dates: list[str] = []
    for m in DATE_RE.finditer(text):
        iso = _to_iso(m.group(1), m.group(2), m.group(3), (m.group(4), m.group(5), m.group(6)))
        if iso and iso not in dates:
            dates.append(iso)

    amounts: list[str] = []
    for m in AMOUNT_RE.finditer(text):
        amt = _parse_amount(m.group(1))
        if amt is not None and amt not in amounts:
            amounts.append(amt)

    organizations: list[dict] = []
    seen_orgs: set[str] = set()
    for m in COUNTERPARTY_RE.finditer(text):
        raw = m.group(0).strip().rstrip(",;.")
        if raw in seen_orgs:
            continue
        seen_orgs.add(raw)
        organizations.append({"raw": raw, "form": m.group(1).upper()})

    vat_rates: list[str] = []
    for m in VAT_RATE_RE.finditer(text):
        rate = m.group(1).replace(",", ".")
        try:
            normalized = str(Decimal(rate).quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            continue
        if normalized not in vat_rates:
            vat_rates.append(normalized)

    return {
        "inns": inns,
        "kpps": kpps,
        "numbers": numbers,
        "dates": dates,
        "amounts": amounts,
        "vat_rates": vat_rates,
        "organizations": organizations,
    }
