from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple
import secrets
import uuid
import jwt

from ..core.config import get_settings
settings = get_settings()

QR_AUD = "trail-checkin"
QR_ISS = "qr-checkin-svc"

def _now():
    return datetime.now(timezone.utc)

def sign_qr(*, trail_id: uuid.UUID, org_id: uuid.UUID, issuer_id: uuid.UUID, ttl_seconds: int | None = None) -> Tuple[str, int]:
    exp = _now() + timedelta(seconds=ttl_seconds or settings.qr_ttl_seconds)
    payload: Dict[str, Any] = {
        "aud": QR_AUD,
        "iss": QR_ISS,
        "jti": secrets.token_urlsafe(16),
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
        "scope": "checkin",
        "trail_id": str(trail_id),
        "org_id": str(org_id),
        "issuer_id": str(issuer_id),  # organiser who generated the QR
    }
    token = jwt.encode(payload, settings.qr_secret_effective, algorithm="HS256")
    return token, int(exp.timestamp())

def verify_qr(token: str) -> Dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.qr_secret_effective,
        algorithms=["HS256"],
        audience=QR_AUD,
        options={"require": ["exp", "aud", "iss"]},
    )
    if payload.get("iss") != QR_ISS:
        raise jwt.InvalidIssuerError("invalid issuer")
    if payload.get("scope") != "checkin":
        raise jwt.InvalidTokenError("invalid scope")
    for k in ("trail_id", "org_id", "issuer_id"):
        if k not in payload:
            raise jwt.InvalidTokenError("missing claim: " + k)
    return payload
