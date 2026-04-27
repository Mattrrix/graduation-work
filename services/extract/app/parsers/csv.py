import io

import pandas as pd


def parse(content: bytes, filename: str) -> dict:
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding="cp1251")
    rows = df.values.tolist()
    headers = df.columns.tolist()
    text = "\n".join(["\t".join(headers), *("\t".join(map(str, r)) for r in rows)]).strip()
    return {
        "text": text,
        "raw": {
            "format": "csv",
            "headers": headers,
            "rows": rows,
        },
    }
