from __future__ import annotations
from typing import Any, Dict, AsyncGenerator
from fastapi import Header, HTTPException, status
import time
import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .core.config import get_settings
from .services.auth_client import acquire_service_token

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


async def trails_get_trail_details(
    *,
    trail_id: str,
    org_id: str | None = None,
    authorization_header: str | None = None,
) -> Dict[str, Any] | None:
    """
    Retrieve a single trail description, favouring a service token scoped to the
    organiser's organisation and falling back to the caller's bearer token.
    """
    headers: Dict[str, str] = {}

    service_token = None
    if org_id:
        service_token = await acquire_service_token(org_ids=[org_id])
    bearer_token: str | None = None
    if service_token:
        bearer_token = service_token
    elif authorization_header and authorization_header.lower().startswith("bearer "):
        bearer_token = authorization_header.split(" ", 1)[1].strip()

    if not bearer_token:
        return None

    headers["Authorization"] = f"Bearer {bearer_token}"
    url = f"{settings.trails_base_url}/trails/{trail_id}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=5.0)
        except Exception:
            return None
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except Exception:
        return None
    return data

async def points_award_checkin(
    *,
    token: str,
    trail_id: str,
    user_id: str,
    org_id: str,
    checked_at: str,
    activity_id: str | None = None,
    activity_order: int | None = None,
    points_delta: int | None = None,
    new_attendance: bool | None = None,
):
    """
    Notify the points service about a completed check-in.

    We prefer a cached service token (so the attendee token never needs organiser scope).
    If service credentials are missing or the mint fails, fall back to the attendee token.
    """
    url = f"{settings.points_base_url}/points/ingest/checkin"
    service_token = await acquire_service_token(org_ids=[org_id])
    auth_token = service_token or token
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    payload = {
        "trail_id": trail_id,
        "user_id": user_id,
        "org_id": org_id,
        "checked_at": checked_at,
    }
    if activity_id is not None:
        payload["activity_id"] = activity_id
    if activity_order is not None:
        payload["activity_order"] = activity_order
    if points_delta is not None:
        payload["points_delta"] = points_delta
    if new_attendance is not None:
        payload["new_attendance"] = new_attendance
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, headers=headers, json=payload, timeout=5.0)
        except Exception:
            pass  # non-blocking for check-in path
