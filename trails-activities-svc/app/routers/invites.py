from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..deps import get_claims, get_db
from ..core.config import get_settings
from ..core.invite import sign_invite, verify_invite
from ..models import Trail, TrailStatus, Registration, RegStatus
from ..schemas import RegistrationRead

router = APIRouter(prefix="/invites", tags=["invites"])
settings = get_settings()

def _ensure_organiser_for_org(claims, org_id: uuid.UUID):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organiser role required")
    if str(org_id) not in [str(x) for x in claims.get("org_ids", [])]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")

async def _get_trail(db: AsyncSession, trail_id: uuid.UUID) -> Trail | None:
    return (await db.execute(select(Trail).where(Trail.id == trail_id))).scalar_one_or_none()

async def _count_confirmed(db: AsyncSession, trail_id: uuid.UUID) -> int:
    q = select(func.count()).select_from(Registration).where(
        Registration.trail_id == trail_id, Registration.status == RegStatus.CONFIRMED
    )
    return (await db.execute(q)).scalar_one()

# --- 1) Organiser creates an invitation link for a trail
@router.post("/trails/{trail_id}", status_code=201)
async def create_invite(
    trail_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_trail(db, trail_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")
    _ensure_organiser_for_org(claims, t.org_id)
    if t.status not in (TrailStatus.PUBLISHED,):
        raise HTTPException(status_code=400, detail="Trail is not inviting registrations")

    token, exp = sign_invite(trail_id=t.id, org_id=t.org_id, inviter_id=uuid.UUID(claims["sub"]))
    return {
        "invite_token": token,
        "expires_at": exp,
        "url": f"{settings.invite_base_url}/{token}",
        "trail_id": str(t.id),
        "org_id": str(t.org_id),
    }

# --- 2) Public: preview an invitation (discover trail details)
@router.get("/{token}")
async def preview_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = verify_invite(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")
    trail_id = uuid.UUID(payload["trail_id"])
    t = await _get_trail(db, trail_id)
    if not t or t.status not in (TrailStatus.PUBLISHED,):
        raise HTTPException(status_code=404, detail="Trail not available")
    # Return minimal discoverable info
    return {
        "trail": {
            "id": str(t.id),
            "org_id": str(t.org_id),
            "title": t.title,
            "description": t.description,
            "starts_at": t.starts_at,
            "ends_at": t.ends_at,
            "location": t.location,
            "capacity": t.capacity,
            "status": t.status.value,
        }
    }

# --- 3) Authenticated: accept an invitation => register current user
@router.post("/{token}/register", response_model=RegistrationRead, status_code=201)
async def accept_invite(
    token: str,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = verify_invite(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")
    trail_id = uuid.UUID(payload["trail_id"])
    org_id = uuid.UUID(payload["org_id"])
    t = await _get_trail(db, trail_id)
    if not t or t.org_id != org_id or t.status not in (TrailStatus.PUBLISHED,):
        raise HTTPException(status_code=404, detail="Trail not available")

    user_id = uuid.UUID(claims["sub"])

    # already registered?
    existing = (await db.execute(select(Registration).where(
        Registration.trail_id == t.id, Registration.user_id == user_id
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Already registered")

    confirmed_count = await _count_confirmed(db, t.id)
    status_val = RegStatus.PENDING if confirmed_count < t.capacity else RegStatus.WAITLISTED

    reg = Registration(
        trail_id=t.id,
        user_id=user_id,
        org_id=t.org_id,
        status=status_val,
        note="via invite",
    )
    db.add(reg)
    await db.commit()
    await db.refresh(reg)
    return RegistrationRead(
        id=reg.id, trail_id=reg.trail_id, user_id=reg.user_id, org_id=reg.org_id,
        status=reg.status.value, note=reg.note
    )