from datetime import date
from decimal import Decimal, InvalidOperation


def inn_checksum_ok(inn: str) -> bool:
    if not inn.isdigit():
        return False
    if len(inn) == 10:
        coef = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        check = sum(int(inn[i]) * coef[i] for i in range(9)) % 11 % 10
        return check == int(inn[9])
    if len(inn) == 12:
        coef1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        coef2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c1 = sum(int(inn[i]) * coef1[i] for i in range(10)) % 11 % 10
        c2 = sum(int(inn[i]) * coef2[i] for i in range(11)) % 11 % 10
        return c1 == int(inn[10]) and c2 == int(inn[11])
    return False


def date_in_range(iso: str) -> bool:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return False
    return date(2000, 1, 1) <= d <= date(2030, 12, 31)


def amount_positive(value: str) -> bool:
    try:
        return Decimal(value) > 0
    except (InvalidOperation, ValueError):
        return False


def validate(fields: dict) -> list[dict]:
    errors: list[dict] = []
    if "inn" in fields and not inn_checksum_ok(fields["inn"]):
        errors.append({"field": "inn", "code": "checksum", "value": fields["inn"]})
    if "date" in fields and not date_in_range(fields["date"]):
        errors.append({"field": "date", "code": "out_of_range", "value": fields["date"]})
    if "amount_total" in fields and not amount_positive(fields["amount_total"]):
        errors.append({"field": "amount_total", "code": "non_positive", "value": fields["amount_total"]})
    return errors
