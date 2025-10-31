from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import secrets
import uuid
import jwt

from .config import get_settings
settings = get_settings()

INVITE_AUD = "trail-invite"
INVITE_ISS = "trails-activities-svc"

def _now() -> datetime:
    return datetime.now(timezone.utc)

def sign_invite(*, trail_id: uuid.UUID, org_id: uuid.UUID, inviter_id: uuid.UUID, ttl_hours: int | None = None) -> tuple[str, int]:
    exp = _now() + timedelta(hours=ttl_hours or settings.invite_ttl_hours)
    payload: Dict[str, Any] = {
        "aud": INVITE_AUD,
        "iss": INVITE_ISS,
        "jti": secrets.token_urlsafe(16),
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
        "scope": "register",
        "trail_id": str(trail_id),
        "org_id": str(org_id),
        "inviter_id": str(inviter_id),
    }
    token = jwt.encode(payload, settings.invite_secret_effective, algorithm="HS256")
    return token, int(exp.timestamp())

def verify_invite(token: str) -> Dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.invite_secret_effective,
        algorithms=["HS256"],
        audience=INVITE_AUD,
        options={"require": ["exp", "aud", "iss"]},
    )
    if payload.get("iss") != INVITE_ISS:
        raise jwt.InvalidIssuerError("invalid issuer")
    if payload.get("scope") != "register":
        raise jwt.InvalidTokenError("invalid scope")
    # basic shape checks
    for k in ("trail_id", "org_id", "inviter_id"):
        if k not in payload:
            raise jwt.InvalidTokenError("missing claim: " + k)
    return payload