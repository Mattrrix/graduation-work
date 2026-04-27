def parse(content: bytes, filename: str) -> dict:
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")
    return {
        "text": text.strip(),
        "raw": {"format": "txt"},
    }
