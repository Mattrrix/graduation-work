"""Сборка dict-описания документа по типу. Writers потом рендерят в нужный формат.

Каждый документ содержит ключ ``parties`` — упорядоченный список словарей-сторон
(структура: role_id, role_label, form, name, inn, kpp, city, is_individual).
Длина списка управляется параметром ``parties`` генератора (от 2 до cap для типа).

Edge-кейсы (множество строк ``edge_cases``) — каждый бьёт по конкретной слабости regex-NER:
    - ``ip_forms`` — превращает стороны в ИП (12-значный ИНН, без КПП). Regex ожидает
      10-значный ИНН + КПП — на ИП присваивает чужой КПП от другого контрагента.
      Режим работы задаётся отдельным параметром ``ip_mode``:
        * ``random`` (по умолчанию) — каждая сторона с вероятностью ~35% становится ИП;
        * ``guaranteed`` — гарантированно ≥1 ИП на документ;
        * ``all`` — все стороны ИП.
    - ``missing_optional`` — у юр.лиц с небольшой вероятностью обнуляется КПП или город.
      Тестирует устойчивость pipeline к разреженным шаблонам.
    - ``multiline_names`` — у части юр.лиц длинное дефисное имя разрывается переносом строки
      («ООО «Альфа-Бета-\\nГамма-Дельта»»). Regex COUNTERPARTY_RE имеет ``\\n`` в исключении
      символов и обрежет имя на первой строке.
    - ``reordered_blocks`` — стороны рендерятся в обратном порядке (Покупатель раньше Продавца).
      Regex берёт ``inns[0]`` как primary ИНН и присвоит роли по позиции — получит зеркальное
      role assignment.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import data
from .inn import gen_inn, gen_kpp


IP_MODE_RANDOM = "random"
IP_MODE_GUARANTEED = "guaranteed"
IP_MODE_ALL = "all"

MISSING_MODE_RANDOM = "random"
MISSING_MODE_GUARANTEED = "guaranteed"
MISSING_MODE_ALL = "all"


ROLES_BY_TYPE: dict[str, list[tuple[str, str]]] = {
    "invoice": [
        ("seller", "Продавец"),
        ("buyer", "Покупатель"),
        ("shipper", "Грузоотправитель"),
        ("consignee", "Грузополучатель"),
    ],
    "upd": [
        ("seller", "Продавец"),
        ("buyer", "Покупатель"),
        ("shipper", "Грузоотправитель"),
        ("consignee", "Грузополучатель"),
    ],
    "waybill": [
        ("shipper", "Грузоотправитель"),
        ("consignee", "Грузополучатель"),
        ("supplier", "Поставщик"),
        ("payer", "Плательщик"),
    ],
    "contract": [
        ("party_a", "Сторона 1"),
        ("party_b", "Сторона 2"),
        ("guarantor", "Поручитель"),
        ("beneficiary", "Бенефициар"),
    ],
    "act": [
        ("contractor", "Исполнитель"),
        ("customer", "Заказчик"),
        ("subcontractor", "Субподрядчик"),
    ],
    "payment_order": [
        ("payer", "Плательщик"),
        ("payee", "Получатель"),
    ],
}

MAX_PARTIES: dict[str, int] = {t: len(roles) for t, roles in ROLES_BY_TYPE.items()}


def _money(value) -> str:
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _date(rng: random.Random, year: int = 2026) -> date:
    start = date(year, 1, 1)
    return start + timedelta(days=rng.randint(0, 364))


def _make_individual(rng: random.Random) -> dict:
    feminine = rng.random() < 0.4
    last_pool = data.IP_LAST_NAMES_FEMININE if feminine else data.IP_LAST_NAMES
    last = rng.choice(last_pool)
    ini1 = rng.choice(data.IP_INITIALS)
    ini2 = rng.choice(data.IP_INITIALS)
    return {
        "form": "ИП",
        "name": f"{last} {ini1}.{ini2}.",
        "inn": gen_inn(rng, 12),
        "kpp": None,
        "city": rng.choice(data.CITIES),
        "is_individual": True,
    }


def _make_legal_entity(
    rng: random.Random,
    edge_cases: set[str],
    *,
    missing_mode: str = MISSING_MODE_RANDOM,
    force_missing: bool = False,
) -> dict:
    use_long = "multiline_names" in edge_cases and rng.random() < 0.45
    if use_long:
        base = rng.choice(data.COMPANY_NAMES_LONG)
        # Разрываем имя после случайного дефиса. Бьёт по COUNTERPARTY_RE — он
        # имеет \n в исключении и обрежет имя на первой строке.
        hyphens = [i for i, ch in enumerate(base) if ch == "-"]
        if hyphens:
            cut = rng.choice(hyphens)
            name = base[: cut + 1] + "\n" + base[cut + 1 :]
        else:
            name = base
    else:
        name = rng.choice(data.COMPANY_NAMES)
    # KPP/city генерируем всегда, потом по режиму обнуляем — детерминизм seed
    # не страдает между modeми, т.к. RNG-состояние не зависит от ветки.
    kpp: str | None = gen_kpp(rng)
    city: str | None = rng.choice(data.CITIES)
    if "missing_optional" in edge_cases:
        if missing_mode == MISSING_MODE_ALL or force_missing:
            kpp = None
            city = None
        else:  # RANDOM или GUARANTEED для не-форсированных индексов
            if rng.random() < 0.20:
                kpp = None
            if rng.random() < 0.15:
                city = None
    return {
        "form": rng.choice(data.COMPANY_FORMS),
        "name": name,
        "inn": gen_inn(rng, 10),
        "kpp": kpp,
        "city": city,
        "is_individual": False,
    }


def _company(
    rng: random.Random,
    edge_cases: set[str],
    *,
    force_individual: bool = False,
    ip_random_prob: float = 0.0,
    missing_mode: str = MISSING_MODE_RANDOM,
    force_missing: bool = False,
) -> dict:
    # force_missing подразумевает «гарантированно ЛЕ с пустыми полями» —
    # сильнее чем ip_random_prob: не должен случайно стать ИП.
    if force_missing:
        is_individual = False
    else:
        is_individual = force_individual or (ip_random_prob > 0 and rng.random() < ip_random_prob)
    if is_individual:
        return _make_individual(rng)
    return _make_legal_entity(
        rng, edge_cases, missing_mode=missing_mode, force_missing=force_missing,
    )


def _make_parties(
    rng: random.Random,
    doc_type: str,
    parties_count: int,
    edge_cases: set[str],
    ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> list[dict]:
    role_specs = ROLES_BY_TYPE[doc_type][:parties_count]
    n = len(role_specs)

    forced_individual_indices: set[int] = set()
    ip_random_prob = 0.0
    if "ip_forms" in edge_cases:
        if ip_mode == IP_MODE_ALL:
            forced_individual_indices = set(range(n))
        elif ip_mode == IP_MODE_GUARANTEED:
            forced_individual_indices.add(rng.randrange(0, n))
            ip_random_prob = 0.35
        else:  # IP_MODE_RANDOM
            ip_random_prob = 0.35

    # missing_mode=guaranteed: один ЛЕ принудительно без КПП и города.
    # Должен быть не-ИП (у ИП и так нет КПП). Если все индексы forced ИП, кейс
    # вырождается — пропускаем (для all-IP документа missing_optional неактуален).
    forced_missing_indices: set[int] = set()
    if "missing_optional" in edge_cases and missing_mode == MISSING_MODE_GUARANTEED:
        le_candidates = [i for i in range(n) if i not in forced_individual_indices]
        if le_candidates:
            forced_missing_indices.add(rng.choice(le_candidates))

    parties: list[dict] = []
    inns_seen: set[str] = set()
    for i, (role_id, role_label) in enumerate(role_specs):
        for _ in range(20):
            c = _company(
                rng,
                edge_cases,
                force_individual=(i in forced_individual_indices),
                ip_random_prob=ip_random_prob,
                missing_mode=missing_mode,
                force_missing=(i in forced_missing_indices),
            )
            if c["inn"] not in inns_seen:
                inns_seen.add(c["inn"])
                break
        c["role_id"] = role_id
        c["role_label"] = role_label
        parties.append(c)
    return parties


def _resolve_parties_count(doc_type: str, requested: int) -> int:
    cap = MAX_PARTIES[doc_type]
    return max(2, min(requested, cap))


def _items(rng: random.Random, count: int | None = None) -> tuple[list[dict], Decimal, Decimal]:
    n = count if count is not None else rng.randint(1, 6)
    items: list[dict] = []
    total = Decimal("0")
    vat_total = Decimal("0")
    for _ in range(n):
        name, unit = rng.choice(data.GOODS)
        qty = rng.randint(1, 20)
        price = Decimal(rng.randint(50, 50000)) + Decimal(rng.randint(0, 99)) / Decimal(100)
        line_sum = (price * qty).quantize(Decimal("0.01"))
        vat = (line_sum * Decimal("0.20")).quantize(Decimal("0.01"))
        items.append({
            "name": name,
            "unit": unit,
            "qty": qty,
            "price": _money(price),
            "sum": _money(line_sum),
            "vat": _money(vat),
        })
        total += line_sum
        vat_total += vat
    return items, total, vat_total


def _reorder_flag(edge_cases: set[str]) -> bool:
    return "reordered_blocks" in edge_cases


def gen_invoice(
    rng: random.Random, *, parties: int = 2,
    edge_cases: set[str] | None = None, ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> dict:
    edge_cases = set(edge_cases or ())
    parties_count = _resolve_parties_count("invoice", parties)
    parties_list = _make_parties(rng, "invoice", parties_count, edge_cases, ip_mode, missing_mode)
    items, total, vat = _items(rng)
    d = _date(rng)
    return {
        "doc_type": "invoice",
        "title": "Счёт-фактура",
        "number": f"INV-{d.year}-{rng.randint(1, 9999):04d}",
        "date": d,
        "parties": parties_list,
        "reorder_blocks": _reorder_flag(edge_cases),
        "items": items,
        "total": _money(total),
        "vat": _money(vat),
        "currency": "RUB",
    }


def gen_act(
    rng: random.Random, *, parties: int = 2,
    edge_cases: set[str] | None = None, ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> dict:
    edge_cases = set(edge_cases or ())
    parties_count = _resolve_parties_count("act", parties)
    parties_list = _make_parties(rng, "act", parties_count, edge_cases, ip_mode, missing_mode)
    service = rng.choice(data.SERVICES)
    amount = Decimal(rng.randint(50000, 5_000_000)) + Decimal(rng.randint(0, 99)) / Decimal(100)
    d = _date(rng)
    return {
        "doc_type": "act",
        "title": "Акт выполненных работ",
        "number": f"АКТ-{d.year}-{rng.randint(1, 999):03d}",
        "date": d,
        "parties": parties_list,
        "reorder_blocks": _reorder_flag(edge_cases),
        "service": service,
        "total": _money(amount),
        "currency": "RUB",
    }


def gen_contract(
    rng: random.Random, *, parties: int = 2,
    edge_cases: set[str] | None = None, ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> dict:
    edge_cases = set(edge_cases or ())
    parties_count = _resolve_parties_count("contract", parties)
    parties_list = _make_parties(rng, "contract", parties_count, edge_cases, ip_mode, missing_mode)
    subject = rng.choice(data.SERVICES)
    amount = Decimal(rng.randint(100_000, 10_000_000))
    d = _date(rng)
    end = d + timedelta(days=rng.randint(30, 365))
    return {
        "doc_type": "contract",
        "title": "Договор",
        "number": f"Д-{d.year}/{rng.randint(1, 999):03d}",
        "date": d,
        "end_date": end,
        "parties": parties_list,
        "reorder_blocks": _reorder_flag(edge_cases),
        "subject": subject,
        "total": _money(amount),
        "currency": "RUB",
    }


def gen_waybill(
    rng: random.Random, *, parties: int = 2,
    edge_cases: set[str] | None = None, ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> dict:
    edge_cases = set(edge_cases or ())
    parties_count = _resolve_parties_count("waybill", parties)
    parties_list = _make_parties(rng, "waybill", parties_count, edge_cases, ip_mode, missing_mode)
    items, total, vat = _items(rng, count=rng.randint(3, 10))
    d = _date(rng)
    return {
        "doc_type": "waybill",
        "title": "Товарная накладная (ТОРГ-12)",
        "number": f"ТН-{d.year}-{rng.randint(1, 9999):04d}",
        "date": d,
        "parties": parties_list,
        "reorder_blocks": _reorder_flag(edge_cases),
        "items": items,
        "total": _money(total),
        "vat": _money(vat),
        "currency": "RUB",
    }


def gen_upd(
    rng: random.Random, *, parties: int = 2,
    edge_cases: set[str] | None = None, ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> dict:
    edge_cases = set(edge_cases or ())
    parties_count = _resolve_parties_count("upd", parties)
    parties_list = _make_parties(rng, "upd", parties_count, edge_cases, ip_mode, missing_mode)
    items, total, vat = _items(rng)
    d = _date(rng)
    return {
        "doc_type": "upd",
        "title": "Универсальный передаточный документ",
        "number": f"УПД-{d.year}-{rng.randint(1, 9999):04d}",
        "date": d,
        "parties": parties_list,
        "reorder_blocks": _reorder_flag(edge_cases),
        "items": items,
        "total": _money(total),
        "vat": _money(vat),
        "currency": "RUB",
    }


def gen_payment_order(
    rng: random.Random, *, parties: int = 2,
    edge_cases: set[str] | None = None, ip_mode: str = IP_MODE_RANDOM,
    missing_mode: str = MISSING_MODE_RANDOM,
) -> dict:
    edge_cases = set(edge_cases or ())
    parties_count = _resolve_parties_count("payment_order", parties)
    parties_list = _make_parties(rng, "payment_order", parties_count, edge_cases, ip_mode, missing_mode)
    amount = Decimal(rng.randint(1_000, 5_000_000)) + Decimal(rng.randint(0, 99)) / Decimal(100)
    d = _date(rng)
    return {
        "doc_type": "payment_order",
        "title": "Платёжное поручение",
        "number": f"{rng.randint(1, 99999):05d}",
        "date": d,
        "parties": parties_list,
        "reorder_blocks": _reorder_flag(edge_cases),
        "purpose": f"Оплата по счёту № INV-{d.year}-{rng.randint(1, 9999):04d}",
        "total": _money(amount),
        "currency": "RUB",
    }


GENERATORS = {
    "invoice": gen_invoice,
    "act": gen_act,
    "contract": gen_contract,
    "waybill": gen_waybill,
    "upd": gen_upd,
    "payment_order": gen_payment_order,
}


SUPPORTED_FORMATS = {
    "invoice": ("pdf", "docx", "xlsx", "csv"),
    "act": ("pdf", "docx"),
    "contract": ("pdf", "docx"),
    "waybill": ("pdf", "xlsx", "csv"),
    "upd": ("pdf", "xlsx"),
    "payment_order": ("pdf", "docx"),
}
