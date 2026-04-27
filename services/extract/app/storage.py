import hashlib
from pathlib import Path

from .config import settings


def storage_root() -> Path:
    root = Path(settings.storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_blob(content: bytes, original_name: str) -> tuple[str, str]:
    sha = hashlib.sha256(content).hexdigest()
    suffix = Path(original_name).suffix.lower()
    bucket = storage_root() / sha[:2]
    bucket.mkdir(parents=True, exist_ok=True)
    path = bucket / f"{sha}{suffix}"
    if not path.exists():
        path.write_bytes(content)
    return sha, str(path)
