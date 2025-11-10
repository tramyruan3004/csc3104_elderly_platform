from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_claims, get_db
from ..models import Attendance
from ..schemas import (
    AttendanceSummary,
    AttendanceTrailSummary,
    AttendanceDailySummary,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _allow_actor_for_org(claims: dict, org_id: UUID) -> bool:
    role = claims.get("role")
    org_ids = {str(x) for x in claims.get("org_ids", []) if x}
    if role in {"organiser", "attend_user"}:
        return str(org_id) in org_ids
    if role == "service":
        return not org_ids or str(org_id) in org_ids
    if role == "admin":
        return True
    return False


@router.get("/orgs/{org_id}/attendance-summary", response_model=AttendanceSummary)
async def org_attendance_summary(
    org_id: UUID,
    days: int = Query(30, ge=1, le=180),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Out of organisation scope")

    now = datetime.now(timezone.utc)
    range_end = now
    range_start = now - timedelta(days=days)

    filters = [
        Attendance.org_id == org_id,
        Attendance.checked_at >= range_start,
        Attendance.checked_at <= range_end,
    ]

    total_row = (
        await db.execute(
            select(
                func.coalesce(func.count(Attendance.id), 0),
                func.coalesce(func.count(func.distinct(Attendance.user_id)), 0),
                func.max(Attendance.checked_at),
            ).where(*filters)
        )
    ).first()
    total_checkins = int(total_row[0]) if total_row else 0
    unique_users = int(total_row[1]) if total_row else 0
    last_checkin = total_row[2] if total_row else None

    trail_rows = (
        await db.execute(
            select(
                Attendance.trail_id,
                func.count(Attendance.id).label("checkins"),
                func.count(func.distinct(Attendance.user_id)).label("unique_participants"),
            )
            .where(*filters)
            .group_by(Attendance.trail_id)
            .order_by(func.count(Attendance.id).desc())
        )
    ).all()
    per_trail = [
        AttendanceTrailSummary(
            trail_id=row.trail_id,
            checkins=int(row.checkins),
            unique_participants=int(row.unique_participants),
        )
        for row in trail_rows
    ]

    daily_rows = (
        await db.execute(
            select(
                func.date_trunc("day", Attendance.checked_at).label("bucket"),
                func.count(Attendance.id).label("checkins"),
            )
            .where(*filters)
            .group_by("bucket")
            .order_by("bucket")
        )
    ).all()
    daily = [
        AttendanceDailySummary(
            day=row.bucket.date(),
            checkins=int(row.checkins),
        )
        for row in daily_rows
    ]

    return AttendanceSummary(
        org_id=org_id,
        range_start=range_start,
        range_end=range_end,
        total_checkins=total_checkins,
        unique_participants=unique_users,
        last_checkin_at=last_checkin,
        per_trail=per_trail,
        daily=daily,
    )
