from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_claims
from ..models import UserPoints, PointsLedger
from ..schemas import BalanceRead, LedgerRead, CheckinIngest
from ..services.points import award_checkin_points, adjust_points

router = APIRouter(prefix="/points", tags=["points"])

def _allow_actor_for_org(claims, org_id: uuid.UUID) -> bool:
    role = claims.get("role")
    org_ids = [str(x) for x in claims.get("org_ids", [])]
    in_scope = (not org_ids) or (str(org_id) in org_ids)  # empty -> global
    return (role == "organiser" and str(org_id) in org_ids) or (role == "service" and in_scope)

@router.get("/users/me/balance", response_model=BalanceRead)
async def my_balance(org_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    up = (await db.execute(select(UserPoints).where(UserPoints.user_id == user_id, UserPoints.org_id == org_id))).scalar_one_or_none()
    if not up:
        return BalanceRead(user_id=user_id, org_id=org_id, balance=0, updated_at=None)  # type: ignore
    return BalanceRead(user_id=up.user_id, org_id=up.org_id, balance=up.balance, updated_at=up.updated_at)

@router.get("/users/me/ledger", response_model=list[LedgerRead])
async def my_ledger(org_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    rows = (await db.execute(select(PointsLedger).where(PointsLedger.user_id == user_id, PointsLedger.org_id == org_id)
                             .order_by(PointsLedger.occurred_at.desc()))).scalars().all()
    return [LedgerRead(id=r.id, delta=r.delta, reason=r.reason, trail_id=r.trail_id, details=r.details, occurred_at=r.occurred_at) for r in rows]

# Ingest from qr-checkin-svc (server-to-server; use organiser or service token)
@router.post("/ingest/checkin")
async def ingest_checkin(payload: CheckinIngest, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    role = claims.get("role")
    if claims.get("role") not in {"organiser", "service"}:
        raise HTTPException(status_code=403, detail="service/organiser required")
    if not _allow_actor_for_org(claims, payload.org_id):
        raise HTTPException(status_code=403, detail="Out of org scope")
    
    # authorise: organiser of org, or service (optionally scoped to org)
    if role == "organiser":
        if str(payload.org_id) not in [str(x) for x in claims.get("org_ids", [])]:
            raise HTTPException(status_code=403, detail="Organiser not in org")
    elif role == "service":
        # Optional: enforce service scoping to org
        pass
    else:
        raise HTTPException(status_code=403, detail="Service or organiser required")

    pts = await award_checkin_points(
        db,
        user_id=payload.user_id,
        org_id=payload.org_id,
        trail_id=payload.trail_id,
        details="qr-checkin"
    )
    return {"awarded": pts}

# Manual adjust (organiser only)
@router.post("/orgs/{org_id}/adjust")
async def adjust_points_admin(org_id: uuid.UUID, user_id: uuid.UUID, delta: int, reason: str = "manual_bonus", claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    try:
        new_balance = await adjust_points(db, user_id=user_id, org_id=org_id, delta=delta, reason=reason)
    except ValueError:
        raise HTTPException(status_code=400, detail="Insufficient points")
    return {"user_id": str(user_id), "org_id": str(org_id), "balance": new_balance}
