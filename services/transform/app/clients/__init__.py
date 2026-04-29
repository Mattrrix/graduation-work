from ..config import settings
from ._base import LLMError

__all__ = ["LLMError", "extract"]


async def extract(text: str, filename: str | None = None) -> dict:
    backend = settings.llm_backend
    if backend == "mlx":
        from . import mlx_local
        return await mlx_local.extract(text, filename)
    if backend == "gigachat":
        from . import gigachat
        return await gigachat.extract(text, filename)
    raise LLMError(f"unknown_llm_backend: {backend!r}")
