from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..deps import get_db, get_claims
from ..models import Registration, RegStatus, Trail, TrailActivity
from ..schemas import RegistrationRead, TrailRead, TrailActivityRead
from .registrations import _registration_to_schema


def _trail_to_schema(entity: Trail) -> TrailRead:
    return TrailRead(
        id=entity.id,
        org_id=entity.org_id,
        created_by=entity.created_by,
        title=entity.title,
        description=entity.description,
        starts_at=entity.starts_at,
        ends_at=entity.ends_at,
        location=entity.location,
        capacity=entity.capacity,
        status=entity.status.value,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )

router = APIRouter(prefix="/users", tags=["users"])


def _activity_to_schema(entity: TrailActivity) -> TrailActivityRead:
    return TrailActivityRead(
        id=entity.id,
        trail_id=entity.trail_id,
        title=entity.title,
        points=entity.points,
        notes=entity.notes,
        order=entity.order,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )

@router.get("/me/registrations")
async def my_registrations(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    regs = (await db.execute(select(Registration).where(Registration.user_id == user_id))).scalars().all()
    return [_registration_to_schema(r) for r in regs]

@router.get("/me/confirmed-trails")
async def my_confirmed_trails(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    rows = (await db.execute(
        select(Trail).join(Registration, Registration.trail_id == Trail.id)
        .where(and_(Registration.user_id == user_id, Registration.status == RegStatus.CONFIRMED))
    )).scalars().all()
    return [_trail_to_schema(t) for t in rows]

@router.get("/me/organiser-trails")
async def my_organiser_trails(
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    user_id = uuid.UUID(claims["sub"])
    rows = (
        await db.execute(
            select(Trail)
            .where(Trail.created_by == user_id)
            .order_by(Trail.updated_at.desc())
            .limit(max(1, min(limit, 100)))
        )
    ).scalars().all()
    return [_trail_to_schema(t) for t in rows]


@router.get("/me/trails/{trail_id}/activities", response_model=list[TrailActivityRead])
async def my_trail_activities(
    trail_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    user_id = uuid.UUID(claims["sub"])
    reg = (
        await db.execute(
            select(Registration).where(
                Registration.trail_id == trail_id,
                Registration.user_id == user_id,
                Registration.status == RegStatus.CONFIRMED,
            )
        )
    ).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=403, detail="Join and confirm the trail before viewing activities")

    rows = (
        await db.execute(
            select(TrailActivity)
            .where(TrailActivity.trail_id == trail_id)
            .order_by(TrailActivity.order.asc())
        )
    ).scalars().all()
    return [_activity_to_schema(row) for row in rows]
