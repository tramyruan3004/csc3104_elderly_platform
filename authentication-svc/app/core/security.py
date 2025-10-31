from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple
import uuid

import jwt
from passlib.context import CryptContext

from .config import get_settings
settings = get_settings()

# Use bcrypt_sha256 to avoid bcrypt 72-byte issues
_pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

def hash_passcode(passcode: str) -> str:
    return _pwd_context.hash(passcode)

def verify_passcode(passcode: str, hashed: str) -> bool:
    return _pwd_context.verify(passcode, hashed)

def make_refresh_token() -> Tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, token_hash

def create_access_token(
    *, user_id: uuid.UUID, role: str, org_ids: list[uuid.UUID], expires_minutes: int | None = None
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes or settings.access_token_exp_minutes)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "org_ids": [str(x) for x in org_ids],
        "iss": settings.token_issuer,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm="RS256")

def create_token_pair(
    *, user_id: uuid.UUID, role: str, org_ids: list[uuid.UUID]
) -> Tuple[str, str, int, str]:
    # Returns: access_token, refresh_token_raw, expires_in_seconds, refresh_token_sha256
    access = create_access_token(user_id=user_id, role=role, org_ids=org_ids)
    refresh_raw, refresh_hash = make_refresh_token()
    return access, refresh_raw, settings.access_token_exp_minutes * 60, refresh_hash

def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_public_key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
