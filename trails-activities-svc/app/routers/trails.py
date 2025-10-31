# app/routers/trails.py  (REPLACE FILE)
from __future__ import annotations

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_claims
from ..models import Trail, TrailStatus, Registration, RegStatus
from ..schemas import TrailCreate, TrailUpdate, TrailRead

router = APIRouter(prefix="/trails", tags=["trails"])

def _ensure_organiser_for_org(claims, org_id: uuid.UUID):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organiser role required")
    if str(org_id) not in [str(x) for x in claims.get("org_ids", [])]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")

@router.get("")
async def list_trails(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID | None = Query(default=None),
    status_filter: TrailStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    stmt = select(Trail)
    if org_id:
        stmt = stmt.where(Trail.org_id == org_id)
    if status_filter:
        stmt = stmt.where(Trail.status == status_filter)
    if date_from:
        stmt = stmt.where(Trail.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Trail.starts_at < date_to)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        TrailRead(
            id=t.id, org_id=t.org_id, title=t.title, description=t.description,
            starts_at=t.starts_at, ends_at=t.ends_at, location=t.location,
            capacity=t.capacity, status=t.status.value
        )
        for t in rows
    ]

@router.get("/{trail_id}", response_model=TrailRead)
async def get_trail(trail_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Trail).where(Trail.id == trail_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")
    return TrailRead(
        id=t.id, org_id=t.org_id, title=t.title, description=t.description,
        starts_at=t.starts_at, ends_at=t.ends_at, location=t.location,
        capacity=t.capacity, status=t.status.value
    )

@router.get("/{trail_id}/attendees")
async def list_attendees(
    trail_id: uuid.UUID,
    status_filter: RegStatus | None = Query(default=RegStatus.CONFIRMED),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    t = (await db.execute(select(Trail).where(Trail.id == trail_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")
    # organiser only for that org
    _ensure_organiser_for_org(claims, t.org_id)

    q = select(Registration).where(Registration.trail_id == trail_id)
    if status_filter:
        q = q.where(Registration.status == status_filter)
    regs = (await db.execute(q)).scalars().all()
    return [
        {"registration_id": r.id, "user_id": r.user_id, "status": r.status.value, "note": r.note}
        for r in regs
    ]

@router.post("/orgs/{org_id}", response_model=TrailRead, status_code=201)
async def create_trail(
    org_id: uuid.UUID,
    payload: TrailCreate,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    _ensure_organiser_for_org(claims, org_id)
    t = Trail(
        org_id=org_id,
        title=payload.title,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        location=payload.location,
        capacity=payload.capacity,
        status=TrailStatus.PUBLISHED,
        created_by=uuid.UUID(claims["sub"]),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return TrailRead(
        id=t.id, org_id=t.org_id, title=t.title, description=t.description,
        starts_at=t.starts_at, ends_at=t.ends_at, location=t.location,
        capacity=t.capacity, status=t.status.value
    )

@router.patch("/{trail_id}", response_model=TrailRead)
async def update_trail(
    trail_id: uuid.UUID,
    payload: TrailUpdate,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    t = (await db.execute(select(Trail).where(Trail.id == trail_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")
    _ensure_organiser_for_org(claims, t.org_id)

    if payload.title is not None: t.title = payload.title
    if payload.description is not None: t.description = payload.description
    if payload.starts_at is not None: t.starts_at = payload.starts_at
    if payload.ends_at is not None: t.ends_at = payload.ends_at
    if payload.location is not None: t.location = payload.location
    if payload.capacity is not None:
        if payload.capacity <= 0:
            raise HTTPException(status_code=400, detail="Capacity must be > 0")
        t.capacity = payload.capacity
    if payload.status is not None:
        try:
            t.status = TrailStatus(payload.status)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid status")

    await db.commit()
    await db.refresh(t)
    return TrailRead(
        id=t.id, org_id=t.org_id, title=t.title, description=t.description,
        starts_at=t.starts_at, ends_at=t.ends_at, location=t.location,
        capacity=t.capacity, status=t.status.value
    )

@router.get("/{trail_id}/registrations/by-user/{user_id}")
async def registration_status_for_user(
    trail_id: uuid.UUID,
    user_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    # 1) Trail must exist
    t = (await db.execute(select(Trail).where(Trail.id == trail_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")

    # 2) Authorize: same user OR organiser in same org
    is_self = (claims.get("sub") == str(user_id))
    is_org = claims.get("role") == "organiser" and str(t.org_id) in [str(x) for x in claims.get("org_ids", [])]
    is_service = (claims.get("role") == "service")
    if not (is_self or is_org or is_service):
        raise HTTPException(status_code=403, detail="Forbidden")

    # 3) Lookup registration
    r = (await db.execute(
        select(Registration).where(
            Registration.trail_id == trail_id,
            Registration.user_id == user_id
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="No registration")

    return {"status": r.status.value}