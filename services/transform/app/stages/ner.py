import re
from datetime import date
from decimal import Decimal, InvalidOperation

INN_RE       = re.compile(r"\b(\d{10}|\d{12})\b")
KPP_RE       = re.compile(r"\b(\d{4}[A-Z\d]{2}\d{3})\b")
NUMBER_RE    = re.compile(r"(?:№|N\.?|номер)\s*([A-ZА-Я0-9][A-ZА-Я0-9\-_/]+)", re.I)
DATE_RE      = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
AMOUNT_RE    = re.compile(r"(?:итого|всего|сумма|к\s+оплате)[^\d]{0,30}([\d\s ]{1,15}(?:[.,]\d{1,2})?)", re.I)
COUNTERPARTY_RE = re.compile(r"\b(?:ООО|ОАО|ЗАО|ИП|ПАО|АО)\s+[«\"']?([^«\"'\n,;()]+)[»\"']?", re.I)


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
    cleaned = s.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def extract(text: str) -> dict:
    fields: dict = {}

    inns = INN_RE.findall(text)
    if inns:
        fields["inn"] = inns[0]

    kpps = KPP_RE.findall(text)
    if kpps:
        fields["kpp"] = kpps[0]

    nm = NUMBER_RE.search(text)
    if nm:
        candidate = nm.group(1).strip()
        if any(c.isdigit() for c in candidate):
            fields["number"] = candidate

    dates: list[str] = []
    for m in DATE_RE.finditer(text):
        iso = _to_iso(m.group(1), m.group(2), m.group(3), (m.group(4), m.group(5), m.group(6)))
        if iso and iso not in dates:
            dates.append(iso)
    if dates:
        fields["date"] = dates[0]
        fields["dates_all"] = dates

    am = AMOUNT_RE.search(text)
    if am:
        amt = _parse_amount(am.group(1))
        if amt is not None:
            fields["amount_total"] = amt

    cp = COUNTERPARTY_RE.search(text)
    if cp:
        fields["counterparty_name"] = cp.group(0).strip().rstrip(",;.")

    return fields
