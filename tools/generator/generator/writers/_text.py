"""Универсальное текстовое представление документа.

Используется и в DOCX, и в первом блоке PDF — единый источник истины для
ключевых слов классификатора и regex NER из transform-сервиса.

Документ содержит ``parties`` — упорядоченный список словарей-сторон с полями
``role_label`` (русское название роли), ``form``, ``name``, ``inn`` и опциональными
``kpp``, ``city``, ``is_individual``.
"""

from __future__ import annotations


def header_lines(d: dict) -> list[str]:
    return [
        d["title"],
        f"№ {d['number']} от {d['date'].strftime('%d.%m.%Y')}",
    ]


def _company_display_lines(party: dict) -> list[str]:
    """Возвращает список строк представления стороны.

    Имя юр.лица может содержать ``\\n`` (edge-кейс multiline_names) — тогда
    кавычки расставляются так, что открывающая «»« уходит на первую строку,
    а закрывающая — на последнюю. Имя реально разрывается переносом.
    """
    if party.get("is_individual"):
        return [f"ИП {party['name']}"]
    parts = party["name"].split("\n")
    if len(parts) == 1:
        return [f"{party['form']} «{parts[0]}»"]
    head = f"{party['form']} «{parts[0]}"
    middle = list(parts[1:-1])
    tail = f"{parts[-1]}»"
    return [head, *middle, tail]


def party_block(party: dict) -> list[str]:
    label = party["role_label"]
    name_lines = _company_display_lines(party)
    out = [f"{label}: {name_lines[0]}"]
    out.extend(name_lines[1:])
    parts = [f"ИНН {party['inn']}"]
    if party.get("kpp"):
        parts.append(f"КПП {party['kpp']}")
    if party.get("city"):
        parts.append(f"г. {party['city']}")
    out.append(", ".join(parts))
    return out


def items_table(items: list[dict]) -> list[list[str]]:
    rows = [["№", "Наименование", "Ед.", "Кол-во", "Цена", "Сумма", "НДС 22%"]]
    for i, it in enumerate(items, 1):
        rows.append([str(i), it["name"], it["unit"], str(it["qty"]), it["price"], it["sum"], it["vat"]])
    return rows


def total_block(d: dict) -> list[str]:
    cur = d.get("currency", "RUB")
    out = [f"Итого: {d['total']} {cur}"]
    if "vat" in d:
        out.append(f"в т.ч. НДС: {d['vat']} {cur}")
    return out


def render_lines(d: dict) -> list[str]:
    """Плоский список строк для DOCX/PDF — все ключевые поля видны парсеру.

    Если на документе поднят флаг ``reorder_blocks`` (edge-кейс reordered_blocks),
    стороны рендерятся в обратном порядке — первый ИНН в тексте принадлежит
    последней роли, regex-NER возьмёт ``inns[0]`` и присвоит роли по позиции,
    получив зеркальное role assignment.
    """
    lines = header_lines(d)
    lines.append("")

    parties_list = list(d.get("parties", []))
    if d.get("reorder_blocks") and len(parties_list) >= 2:
        parties_list.reverse()
    for party in parties_list:
        lines += party_block(party)

    t = d["doc_type"]
    if t == "act":
        lines.append("")
        lines.append(f"Предмет: {d['service']}")
    elif t == "contract":
        lines.append("")
        lines.append(f"Срок действия: до {d['end_date'].strftime('%d.%m.%Y')}")
        lines.append(f"Предмет договора: {d['subject']}")
    elif t == "payment_order":
        lines.append("")
        lines.append(f"Назначение платежа: {d['purpose']}")

    lines.append("")
    lines += total_block(d)
    return lines
