from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Checkin, ActivityCheckin

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


async def record_activity_checkin(
    db: AsyncSession,
    *,
    trail_id: uuid.UUID,
    activity_id: uuid.UUID,
    user_id: uuid.UUID,
    activity_order: int | None = None,
    points_awarded: int = 0,
):
    existing = (
        await db.execute(
            select(ActivityCheckin).where(
                ActivityCheckin.activity_id == activity_id,
                ActivityCheckin.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False

    obj = ActivityCheckin(
        trail_id=trail_id,
        activity_id=activity_id,
        user_id=user_id,
        activity_order=activity_order,
        points_awarded=points_awarded,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj, True
