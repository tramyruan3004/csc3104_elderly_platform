# app/routers/registrations.py  (REPLACE FILE)
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..deps import get_db, get_claims
from ..models import Trail, TrailStatus, Registration, RegStatus
from ..schemas import RegistrationCreateSelf, RegistrationCreateByOrganiser, RegistrationRead

router = APIRouter(prefix="/registrations", tags=["registrations"])

def _ensure_organiser_for_trail(claims, trail: Trail):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organiser role required")
    if str(trail.org_id) not in [str(x) for x in claims.get("org_ids", [])]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")

async def _get_trail(db: AsyncSession, trail_id: uuid.UUID) -> Trail | None:
    return (await db.execute(select(Trail).where(Trail.id == trail_id))).scalar_one_or_none()

async def _count_confirmed(db: AsyncSession, trail_id: uuid.UUID) -> int:
    q = select(func.count()).select_from(Registration).where(
        Registration.trail_id == trail_id, Registration.status == RegStatus.CONFIRMED
    )
    return (await db.execute(q)).scalar_one()

@router.post("/trails/{trail_id}/self", response_model=RegistrationRead, status_code=201)
async def self_register(
    trail_id: uuid.UUID,
    payload: RegistrationCreateSelf,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_trail(db, trail_id)
    if not t or t.status not in (TrailStatus.PUBLISHED,):
        raise HTTPException(status_code=404, detail="Trail not available")

    user_id = uuid.UUID(claims["sub"])
    existing = (await db.execute(select(Registration).where(
        Registration.trail_id == t.id, Registration.user_id == user_id
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Already registered")

    confirmed_count = await _count_confirmed(db, t.id)
    status_val = RegStatus.PENDING if confirmed_count < t.capacity else RegStatus.WAITLISTED

    reg = Registration(trail_id=t.id, user_id=user_id, org_id=t.org_id, status=status_val, note=payload.note)
    db.add(reg)
    await db.commit()
    await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )

@router.post("/trails/{trail_id}/by-organiser", response_model=RegistrationRead, status_code=201)
async def organiser_register(
    trail_id: uuid.UUID,
    payload: RegistrationCreateByOrganiser,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_trail(db, trail_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")
    _ensure_organiser_for_trail(claims, t)
    if t.status not in (TrailStatus.PUBLISHED,):
        raise HTTPException(status_code=400, detail="Trail is not accepting registrations")

    existing = (await db.execute(select(Registration).where(
        Registration.trail_id == t.id, Registration.user_id == payload.user_id
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Already registered")

    confirmed_count = await _count_confirmed(db, t.id)
    status_val = RegStatus.PENDING if confirmed_count < t.capacity else RegStatus.WAITLISTED

    reg = Registration(trail_id=t.id, user_id=payload.user_id, org_id=t.org_id, status=status_val, note=payload.note)
    db.add(reg)
    await db.commit()
    await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )

@router.post("/{registration_id}/approve", response_model=RegistrationRead)
async def approve_registration(
    registration_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    reg = (await db.execute(select(Registration).where(Registration.id == registration_id))).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    t = await _get_trail(db, reg.trail_id)
    _ensure_organiser_for_trail(claims, t)

    if reg.status not in (RegStatus.PENDING, RegStatus.WAITLISTED):
        raise HTTPException(status_code=400, detail="Only pending/waitlisted can be approved")
    reg.status = RegStatus.APPROVED
    await db.commit(); await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )

@router.post("/{registration_id}/confirm", response_model=RegistrationRead)
async def confirm_registration(
    registration_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    reg = (await db.execute(select(Registration).where(Registration.id == registration_id))).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    t = await _get_trail(db, reg.trail_id)
    _ensure_organiser_for_trail(claims, t)

    if t.status not in (TrailStatus.PUBLISHED, TrailStatus.CLOSED):
        raise HTTPException(status_code=400, detail="Trail not in confirmable state")

    if reg.status not in (RegStatus.APPROVED, RegStatus.PENDING):
        raise HTTPException(status_code=400, detail="Only approved/pending can be confirmed")

    confirmed_count = await _count_confirmed(db, t.id)
    if confirmed_count >= t.capacity:
        raise HTTPException(status_code=409, detail="Trail capacity full")

    reg.status = RegStatus.CONFIRMED
    await db.commit(); await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )

@router.post("/{registration_id}/reject", response_model=RegistrationRead)
async def reject_registration(
    registration_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    reg = (await db.execute(select(Registration).where(Registration.id == registration_id))).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    t = await _get_trail(db, reg.trail_id)
    _ensure_organiser_for_trail(claims, t)

    if reg.status not in (RegStatus.PENDING, RegStatus.APPROVED, RegStatus.WAITLISTED):
        raise HTTPException(status_code=400, detail="Only pending/approved/waitlisted can be rejected")
    reg.status = RegStatus.REJECTED
    await db.commit(); await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )

@router.post("/{registration_id}/cancel", response_model=RegistrationRead)
async def organiser_cancel_registration(
    registration_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    reg = (await db.execute(select(Registration).where(Registration.id == registration_id))).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    t = await _get_trail(db, reg.trail_id)
    _ensure_organiser_for_trail(claims, t)

    if reg.status in (RegStatus.CANCELLED, RegStatus.REJECTED):
        raise HTTPException(status_code=400, detail="Already inactive")
    reg.status = RegStatus.CANCELLED
    await db.commit(); await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )

@router.delete("/{registration_id}", status_code=204)
async def cancel_own_registration(
    registration_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    reg = (await db.execute(select(Registration).where(Registration.id == registration_id))).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    if str(reg.user_id) != claims["sub"]:
        raise HTTPException(status_code=403, detail="Not your registration")
    reg.status = RegStatus.CANCELLED
    await db.commit()
    return