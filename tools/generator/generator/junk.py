"""Негативные документы для проверки F-T13 и устойчивости пайплайна."""

from __future__ import annotations

import random
from pathlib import Path

from . import data


def _salt(rng: random.Random) -> str:
    return f"\n# {rng.randint(10**12, 10**13 - 1)}\n"


def junk_irrelevant_text(rng: random.Random) -> tuple[str, str, bytes]:
    text = rng.choice(data.JUNK_TEXTS) + _salt(rng)
    return ("junk-text", "txt", text.encode("utf-8"))


def junk_empty_file(rng: random.Random) -> tuple[str, str, bytes]:
    return ("junk-empty", "txt", b"")


def junk_garbled_pdf(rng: random.Random) -> tuple[str, str, bytes]:
    tail = f" // {rng.randint(10**12, 10**13 - 1)}".encode()
    return ("junk-garbled", "pdf", b"%PDF-1.4 not really a pdf, just bytes" + tail)


def junk_wrong_extension(rng: random.Random) -> tuple[str, str, bytes]:
    text = rng.choice(data.JUNK_TEXTS) + _salt(rng)
    return ("junk-wrong-ext", "docx", text.encode("utf-8"))


JUNK_GENERATORS = [
    junk_irrelevant_text,
    junk_empty_file,
    junk_garbled_pdf,
    junk_wrong_extension,
]


def write_junk(out_dir: Path, count: int, rng: random.Random) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan: list = []
    if count >= len(JUNK_GENERATORS):
        plan.extend(JUNK_GENERATORS)
        for _ in range(count - len(JUNK_GENERATORS)):
            plan.append(rng.choice(JUNK_GENERATORS))
    else:
        plan = [rng.choice(JUNK_GENERATORS) for _ in range(count)]
    rng.shuffle(plan)

    paths: list[Path] = []
    for i, kind_fn in enumerate(plan):
        prefix, ext, payload = kind_fn(rng)
        path = out_dir / f"{prefix}-{i + 1:03d}.{ext}"
        path.write_bytes(payload)
        paths.append(path)
    return paths
