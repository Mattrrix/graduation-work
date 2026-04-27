import re
from decimal import Decimal, InvalidOperation


_LEGAL_FORMS = ("ООО", "ОАО", "ЗАО", "ПАО", "АО", "ИП")


def normalize_amount(value: str) -> str | None:
    try:
        return str(Decimal(str(value).replace(" ", "").replace(",", ".")).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def normalize_counterparty(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip(" ,;.")
    cleaned = cleaned.replace("«", "\"").replace("»", "\"")
    return cleaned


def normalize(fields: dict) -> dict:
    out = dict(fields)
    if "amount_total" in out:
        normalized = normalize_amount(out["amount_total"])
        if normalized:
            out["amount_total"] = normalized
    if "counterparty_name" in out:
        out["counterparty_name"] = normalize_counterparty(out["counterparty_name"])
    return out
