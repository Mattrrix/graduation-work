import json
import re

PROMPT_TEMPLATE = """Ты извлекаешь структурированные данные из русскоязычного бизнес-документа \
(счёт-фактура, акт, договор, ТОРГ-12, УПД, платёжное поручение).

Имя файла: {filename}
(Имя файла часто содержит подсказку о типе — например "invoice-...", "акт-..." \
или "contract-...". Используй его как ВТОРОЙ источник информации, но \
ВЕРИФИЦИРУЙ против содержимого. Если содержимое явно противоречит имени, доверяй содержимому. \
Имя файла само по себе НЕ является доказательством типа.)

Документ:
\"\"\"
{text}
\"\"\"

Верни СТРОГО один JSON-объект без обрамления ```. Поля и допустимые значения:
{{
  "doc_type": "invoice|act|contract|waybill|upd|payment_order|null",
  "doc_type_confidence": 0.0,
  "counterparties": [
    {{
      "name": "полное имя организации, как в документе",
      "form": "ООО|ОАО|ЗАО|ИП|ПАО|АО|null",
      "inn": "10 или 12 цифр или null",
      "kpp": "9 символов или null",
      "role": "продавец|покупатель|плательщик|получатель|исполнитель|заказчик|поставщик|грузоотправитель|грузополучатель|банк|null",
      "is_primary": false
    }}
  ],
  "dates": [
    {{ "value": "YYYY-MM-DD", "role": "doc_date|due_date|delivery_date|null" }}
  ],
  "amounts": [
    {{ "value": "12345.67", "role": "total|vat" }}
  ],
  "doc_number": "значение или null",
  "vat_rate": "число процентов или null",
  "summary": "одно короткое предложение о документе (тип + о чём + ключевая сторона)"
}}

Правила:
- ровно один контрагент должен быть is_primary=true (главная сторона по типу документа: \
продавец для счёт-фактуры, плательщик для платёжного поручения, исполнитель для акта, и т.п.)
- если поле в документе отсутствует, пустое или прочерки — верни null, не выдумывай
- ИНН только цифры
- date в ISO YYYY-MM-DD
- amount в формате "12345.67" (точка как разделитель, без пробелов и валюты)
- В amounts возвращай РОВНО ДВЕ итоговые суммы документа (или одну, если другой нет в документе):
  • total — итоговая сумма документа с НДС (фразы "Итого к оплате", "Всего с НДС", "К оплате")
  • vat — итоговая сумма НДС по всему документу (если выделена отдельно строкой "Итого НДС", "Всего НДС", "В том числе НДС"). Это ОДНА итоговая цифра НДС, не построчно.
  НЕ возвращай: построчные суммы товаров, ставки НДС в процентах, авансы, sub-total без НДС, промежуточные итоги по разделам.
- vat_rate — только число процентной ставки НДС (например "22" для НДС 22%), без знака %
- если ничего из списка doc_type не подходит — верни null с doc_type_confidence=0
- doc_type_confidence: 0.0..1.0, насколько ты уверен в типе с учётом и содержимого, и имени файла"""


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def strip_fences(s: str) -> str:
    no_fences = _FENCE_RE.sub("", s).strip()
    m = _JSON_BLOCK_RE.search(no_fences)
    return m.group(0) if m else no_fences


def build_prompt(text: str, filename: str | None, max_chars: int) -> str:
    return PROMPT_TEMPLATE.format(
        text=text[:max_chars],
        filename=filename or "(не указано)",
    )


_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def _strip_line_comments(s: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if escape:
            out.append(c)
            escape = False
            i += 1
            continue
        if c == "\\":
            out.append(c)
            escape = True
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            out.append(c)
            i += 1
            continue
        if not in_string and c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")

_VALID_DOC_TYPES = {"invoice", "act", "contract", "waybill", "upd", "payment_order"}

_DOC_TYPE_ALIASES = {
    "торг-12": "waybill",
    "торг12": "waybill",
    "торг 12": "waybill",
    "товарная накладная": "waybill",
    "накладная": "waybill",
    "счёт-фактура": "invoice",
    "счет-фактура": "invoice",
    "счёт фактура": "invoice",
    "счет фактура": "invoice",
    "акт": "act",
    "акт выполненных работ": "act",
    "акт оказанных услуг": "act",
    "договор": "contract",
    "упд": "upd",
    "универсальный передаточный документ": "upd",
    "платёжное поручение": "payment_order",
    "платежное поручение": "payment_order",
}


def _normalize_doc_type(value):
    if not value or not isinstance(value, str):
        return value
    v = value.strip().lower()
    if v in _VALID_DOC_TYPES:
        return v
    return _DOC_TYPE_ALIASES.get(v, value)


def tolerant_json_loads(s: str) -> dict:
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        cleaned = s.translate(_SMART_QUOTES)
        cleaned = _strip_line_comments(cleaned)
        cleaned = _TRAILING_COMMA_RE.sub(r"\1", cleaned)
        data = json.loads(cleaned)
    if isinstance(data, dict) and "doc_type" in data:
        data["doc_type"] = _normalize_doc_type(data["doc_type"])
    return data
