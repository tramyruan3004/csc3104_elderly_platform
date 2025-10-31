from __future__ import annotations

import time
from typing import Any, Dict, AsyncGenerator

import httpx
import jwt
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .db import get_session

settings = get_settings()

# simple in-memory JWKS cache
_JWKS: Dict[str, Any] | None = None
_JWKS_TS: float = 0.0
_JWKS_TTL: int = 3600  # seconds

async def fetch_jwks() -> Dict[str, Any]:
    global _JWKS, _JWKS_TS
    now = time.time()
    if _JWKS is None or (now - _JWKS_TS) > _JWKS_TTL:
        async with httpx.AsyncClient() as client:
            r = await client.get(settings.auth_jwks_url, timeout=5.0)
            r.raise_for_status()
            _JWKS = r.json()
            _JWKS_TS = now
    return _JWKS

async def get_signing_key():
    from jwt.algorithms import RSAAlgorithm
    jwks = await fetch_jwks()
    # If multiple keys, you can pick by 'kid'; here we take the first
    key = jwks["keys"][0]
    return RSAAlgorithm.from_jwk(key)

async def get_claims(authorization: str | None = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    key = await get_signing_key()
    try:
        payload = jwt.decode(token, key=key, algorithms=["RS256"], options={"verify_aud": False})
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    # basic shape check
    if "sub" not in payload or "role" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    # normalize org_ids
    if "org_ids" not in payload or not isinstance(payload["org_ids"], list):
        payload["org_ids"] = []
    return payload

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session
