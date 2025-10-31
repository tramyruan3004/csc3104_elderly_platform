from __future__ import annotations
from typing import Any, Dict, AsyncGenerator
from fastapi import Header, HTTPException, status
import time
import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .core.config import get_settings

settings = get_settings()

_JWKS: Dict[str, Any] | None = None
_JWKS_TS: float = 0.0
_JWKS_TTL: int = 3600

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
    if "sub" not in payload or "role" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    if "org_ids" not in payload or not isinstance(payload["org_ids"], list):
        payload["org_ids"] = []
    return payload

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_session():
        yield s

# --- outbound clients ---

async def trails_get_registration_status(*, token: str, trail_id: str, user_id: str) -> str | None:
    """Return status string or None."""
    url = f"{settings.trails_base_url}/trails/{trail_id}/registrations/by-user/{user_id}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers, timeout=5.0)
        if r.status_code == 200:
            return r.json().get("status")
        return None

async def points_award_checkin(*, token: str, trail_id: str, user_id: str, org_id: str, checked_at: str):
    url = f"{settings.points_base_url}/points/ingest/checkin"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"trail_id": trail_id, "user_id": user_id, "org_id": org_id, "checked_at": checked_at}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, headers=headers, json=payload, timeout=5.0)
        except Exception:
            pass  # non-blocking for check-in path
