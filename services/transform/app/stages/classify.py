import re

RULES: list[tuple[str, list[re.Pattern]]] = [
    ("payment_order", [
        re.compile(r"\bплат[её]жное\s+поручение\b", re.I),
    ]),
    ("upd", [
        re.compile(r"\bуниверсальный\s+передаточный\s+документ\b", re.I),
        re.compile(r"\bУПД[\s\-_]*[\dN№]", re.I),
    ]),
    ("waybill", [
        re.compile(r"\bТОРГ[\s\-]*12\b", re.I),
        re.compile(r"\bтоварная\s+накладная\b", re.I),
    ]),
    ("act", [
        re.compile(r"\bакт\s+(?:№|N|выполненных|оказанных|приёмки|сдачи)", re.I),
    ]),
    ("contract", [
        re.compile(r"\bдоговор[\s№N]", re.I),
        re.compile(r"\bконтракт[\s№N]", re.I),
    ]),
    ("invoice", [
        re.compile(r"\bсч[её]т[\s\-]*фактур[аы]\b[^.\n]{0,80}(?:№|\d)", re.I),
        re.compile(r"\bсч[её]т\s+(?:№|на\s+оплату)", re.I),
    ]),
]


FILENAME_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("payment_order", ("payment_order", "payment-order", "плат")),
    ("upd", ("upd", "упд")),
    ("waybill", ("waybill", "торг", "накладн")),
    ("invoice", ("invoice", "счет", "счёт")),
    ("act", ("act", "акт")),
    ("contract", ("contract", "договор")),
]


def classify(text: str, filename: str | None = None) -> str | None:
    haystack = (text or "")[:5000]
    for doc_type, patterns in RULES:
        for pat in patterns:
            if pat.search(haystack):
                return doc_type
    if filename:
        lower = filename.lower()
        for doc_type, hints in FILENAME_HINTS:
            if any(h in lower for h in hints):
                return doc_type
    return None
