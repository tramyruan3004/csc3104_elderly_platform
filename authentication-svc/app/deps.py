from __future__ import annotations

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from uuid import UUID

from .db import get_session
from .core.config import get_settings
from .models import User, UserRole
from sqlalchemy import select

settings = get_settings()

async def get_db() -> AsyncSession:
    async for s in get_session():
        return s


async def get_current_user(
    authorization: str | None = Header(default=None),   # ⬅ read HTTP header
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        sub = UUID(payload["sub"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = (await db.execute(select(User).where(User.id == sub))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")
    return user


async def require_organiser(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ORGANISER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organiser role required")
    return user