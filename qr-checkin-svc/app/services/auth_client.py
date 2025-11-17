from __future__ import annotations

import asyncio
import time
from typing import Sequence

import httpx

from ..core.config import get_settings

settings = get_settings()

_service_token_lock = asyncio.Lock()
_service_token_value: str | None = None
_service_token_exp: float = 0.0


async def acquire_service_token(org_ids: Sequence[str] | None = None) -> str | None:
    """Return a cached service token scoped to optional org IDs."""
    if not settings.service_client_id or not settings.service_client_secret:
        return None

    now = time.time()
    global _service_token_value, _service_token_exp

    if _service_token_value and now < _service_token_exp - 15:
        return _service_token_value

    async with _service_token_lock:
        if _service_token_value and time.time() < _service_token_exp - 15:
            return _service_token_value

        url = settings.auth_base_url.rstrip("/") + "/auth/service-token"
        payload = {
            "client_id": settings.service_client_id,
            "client_secret": settings.service_client_secret,
        }
        if org_ids:
            payload["org_ids"] = list(org_ids)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=5.0)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return None

        token = data.get("access_token")
        if not token:
            return None
        expires_in = data.get("expires_in") or 900

        _service_token_value = token
        _service_token_exp = time.time() + expires_in
        return token
