from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..deps import get_db, get_claims
from ..models import Registration, RegStatus, Trail
from ..schemas import RegistrationRead, TrailRead

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me/registrations")
async def my_registrations(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    regs = (await db.execute(select(Registration).where(Registration.user_id == user_id))).scalars().all()
    return [
        RegistrationRead(
            id=r.id, trail_id=r.trail_id, user_id=r.user_id, org_id=r.org_id,
            status=r.status.value, note=r.note
        ) for r in regs
    ]

@router.get("/me/confirmed-trails")
async def my_confirmed_trails(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    rows = (await db.execute(
        select(Trail).join(Registration, Registration.trail_id == Trail.id)
        .where(and_(Registration.user_id == user_id, Registration.status == RegStatus.CONFIRMED))
    )).scalars().all()
    return [
        TrailRead(
            id=t.id, org_id=t.org_id, title=t.title, description=t.description,
            starts_at=t.starts_at, ends_at=t.ends_at, location=t.location,
            capacity=t.capacity, status=t.status.value
        ) for t in rows
    ]
