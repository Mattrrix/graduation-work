from __future__ import annotations

import csv
from pathlib import Path

from . import _text


def write(d: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Поле", "Значение"])
        w.writerow(["Документ", d["title"]])
        w.writerow(["Номер", d["number"]])
        w.writerow(["Дата", d["date"].strftime("%d.%m.%Y")])
        for line in _text.render_lines(d)[2:]:
            if not line:
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                w.writerow([key.strip(), value.strip()])
            else:
                w.writerow(["", line])
        if "items" in d and d["items"]:
            w.writerow([])
            for row in _text.items_table(d["items"]):
                w.writerow(row)
