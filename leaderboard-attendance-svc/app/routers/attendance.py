from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..deps import get_claims, get_db
from ..models import Attendance
from ..schemas import AttendanceRow

router = APIRouter(prefix="/attendance", tags=["attendance"])

def _allow_actor_for_org(claims: dict, org_id: uuid.UUID) -> bool:
    """Allow organiser within org or service with matching org scope."""
    role = claims.get("role")
    org_ids = [str(x) for x in claims.get("org_ids", [])]
    in_scope = (not org_ids) or (str(org_id) in org_ids)  # empty means global service
    return (role == "organiser" and str(org_id) in org_ids) or (role == "service" and in_scope)

# Organiser view: list all check-ins for a trail (or whole org by period via query later)
@router.get("/trails/{trail_id}", response_model=list[AttendanceRow])
async def trail_roster(trail_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser or Service not in org")

    rows = (await db.execute(
        select(Attendance).where(Attendance.trail_id == trail_id).order_by(Attendance.checked_at.asc())
    )).scalars().all()
    return [AttendanceRow(id=r.id, trail_id=r.trail_id, org_id=r.org_id, user_id=r.user_id, checked_at=r.checked_at) for r in rows]

# Attendee history
@router.get("/users/me", response_model=list[AttendanceRow])
async def my_attendance(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    uid = uuid.UUID(claims["sub"])
    rows = (await db.execute(
        select(Attendance).where(Attendance.user_id == uid).order_by(Attendance.checked_at.desc())
    )).scalars().all()
    return [AttendanceRow(id=r.id, trail_id=r.trail_id, org_id=r.org_id, user_id=r.user_id, checked_at=r.checked_at) for r in rows]
