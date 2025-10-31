from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Checkin

async def record_checkin(
    db: AsyncSession,
    *,
    trail_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    checked_by: uuid.UUID | None = None,
    method: str = "qr",
):
    # idempotent: if exists, return existing
    existing = (await db.execute(
        select(Checkin).where(Checkin.trail_id == trail_id, Checkin.user_id == user_id)
    )).scalar_one_or_none()
    if existing:
        return existing, False

    obj = Checkin(trail_id=trail_id, org_id=org_id, user_id=user_id, checked_by=checked_by, method=method)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj, True
