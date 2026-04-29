FILENAME_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("payment_order", ("payment_order", "payment-order", "плат")),
    ("upd", ("upd", "упд")),
    ("waybill", ("waybill", "торг", "накладн")),
    ("invoice", ("invoice", "счет", "счёт")),
    ("act", ("act", "акт")),
    ("contract", ("contract", "договор")),
]


def filename_hint(filename: str | None) -> str | None:
    if not filename:
        return None
    lower = filename.lower()
    for doc_type, hints in FILENAME_HINTS:
        if any(h in lower for h in hints):
            return doc_type
    return None
