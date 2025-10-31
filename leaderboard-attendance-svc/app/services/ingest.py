from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Attendance, UserMonthlyStats, ym_from_dt

def _now():
    return datetime.now(timezone.utc)

async def ingest_checkin_evt(
    db: AsyncSession,
    *,
    trail_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    checked_at: datetime | None = None,
):
    """
    Idempotent insert into Attendance (unique trail_id+user_id).
    Then increment per-user monthly aggregates for both org scope and system scope.
    """
    dt = checked_at or _now()

    # 1) raw row (idempotent on trail_id+user_id)
    exists = (await db.execute(
        select(Attendance).where(Attendance.trail_id == trail_id, Attendance.user_id == user_id)
    )).scalar_one_or_none()
    if not exists:
        db.add(Attendance(trail_id=trail_id, org_id=org_id, user_id=user_id, checked_at=dt))

    ym = ym_from_dt(dt)

    # 2) org scoped stats
    await _inc_user_stats(db, ym=ym, org_id=org_id, user_id=user_id, checkins_delta=1)

    # 3) system scoped stats (org_id None)
    await _inc_user_stats(db, ym=ym, org_id=None, user_id=user_id, checkins_delta=1)

    await db.commit()

async def _inc_user_stats(
    db: AsyncSession, *, ym: int, org_id: uuid.UUID | None, user_id: uuid.UUID, checkins_delta: int = 0, points_delta: int = 0
):
    row = (await db.execute(
        select(UserMonthlyStats).where(
            UserMonthlyStats.ym == ym,
            UserMonthlyStats.org_id.is_(org_id) if org_id is None else UserMonthlyStats.org_id == org_id,
            UserMonthlyStats.user_id == user_id
        )
    )).scalar_one_or_none()

    if row is None:
        row = UserMonthlyStats(ym=ym, org_id=org_id, user_id=user_id, checkins=0, points=0)
        db.add(row)

    # apply deltas
    row.checkins = int(row.checkins) + checkins_delta
    row.points = int(row.points) + points_delta
