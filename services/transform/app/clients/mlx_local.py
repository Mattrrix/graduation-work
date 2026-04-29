import logging

import httpx

from ..config import settings
from . import _prompt
from ._base import LLMError

logger = logging.getLogger(__name__)


async def extract(text: str, filename: str | None = None) -> dict:
    prompt = _prompt.build_prompt(text, filename, settings.qwen_max_input_chars)
    payload = {
        "model": settings.qwen_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": settings.qwen_max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    try:
        async with httpx.AsyncClient(timeout=settings.qwen_timeout) as client:
            resp = await client.post(
                f"{settings.qwen_url.rstrip('/')}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as e:
        raise LLMError(f"http_error: {e}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"unexpected_response_shape: {e}") from e

    cleaned = _prompt.strip_fences(content)
    try:
        return _prompt.tolerant_json_loads(cleaned)
    except Exception as e:
        logger.warning("mlx_local invalid json: %s | head=%r", e, cleaned[:200])
        raise LLMError(f"invalid_json: {e}") from e
