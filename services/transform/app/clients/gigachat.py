import asyncio
import logging
import time
import uuid

import httpx

from ..config import settings
from . import _prompt
from ._base import LLMError

logger = logging.getLogger(__name__)


_token_lock = asyncio.Lock()
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


async def _get_access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    async with _token_lock:
        now = time.time()
        if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
            return _token_cache["access_token"]

        if not settings.gigachat_auth_key:
            raise LLMError("gigachat_auth_key_missing")

        headers = {
            "Authorization": f"Basic {settings.gigachat_auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        body = f"scope={settings.gigachat_scope}"

        try:
            async with httpx.AsyncClient(
                timeout=settings.gigachat_timeout,
                verify=settings.gigachat_verify_ssl,
            ) as client:
                resp = await client.post(settings.gigachat_oauth_url, headers=headers, content=body)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise LLMError(f"gigachat_oauth_http_error: {e}") from e

        token = data.get("access_token")
        if not token:
            raise LLMError(f"gigachat_oauth_no_token: {data!r}")

        expires_ms = data.get("expires_at") or 0
        _token_cache["access_token"] = token
        _token_cache["expires_at"] = (expires_ms / 1000.0) if expires_ms else (now + 1800)
        return token


async def extract(text: str, filename: str | None = None, *, model_override: str | None = None) -> dict:
    prompt = _prompt.build_prompt(text, filename, settings.gigachat_max_input_chars)
    payload = {
        "model": model_override or settings.gigachat_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": settings.gigachat_max_tokens,
    }

    token = await _get_access_token()
    url = f"{settings.gigachat_chat_base.rstrip('/')}/api/v1/chat/completions"
    auth_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(
            timeout=settings.gigachat_timeout,
            verify=settings.gigachat_verify_ssl,
        ) as client:
            resp = await client.post(url, json=payload, headers=auth_headers)
            if resp.status_code == 401:
                _token_cache["access_token"] = None
                token = await _get_access_token()
                auth_headers["Authorization"] = f"Bearer {token}"
                resp = await client.post(url, json=payload, headers=auth_headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as e:
        raise LLMError(f"gigachat_chat_http_error: {e}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"gigachat_unexpected_response: {e}") from e

    cleaned = _prompt.strip_fences(content)
    try:
        return _prompt.tolerant_json_loads(cleaned)
    except Exception as e:
        logger.warning("gigachat invalid json: %s | head=%r", e, cleaned[:200])
        raise LLMError(f"gigachat_invalid_json: {e}") from e
