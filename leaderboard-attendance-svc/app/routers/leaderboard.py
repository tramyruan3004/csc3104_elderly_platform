from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from ..deps import get_claims, get_db
from ..models import OrgMonthlyRank, SystemMonthlyRank
from ..schemas import LeaderRow
from ..services.ranks import rebuild_ranks_for_period
from datetime import datetime

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

def current_ym() -> int:
    now = datetime.utcnow()
    return now.year * 100 + now.month

def _allow_actor_for_org(claims: dict, org_id: UUID) -> bool:
    """Allow organiser within org or service with matching org scope."""
    role = claims.get("role")
    org_ids = [str(x) for x in claims.get("org_ids", [])]
    in_scope = (not org_ids) or (str(org_id) in org_ids)  # empty means global service
    return (role == "organiser" and str(org_id) in org_ids) or (role == "service" and in_scope)

@router.get("/system", response_model=list[LeaderRow])
async def system_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    ym: int | None = None,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db)
):
    # Any authenticated user can view
    ymv = ym or current_ym()
    # ensure ranks exist (cheap and safe to rebuild on-demand)
    await rebuild_ranks_for_period(db, ymv)
    rows = (await db.execute(
        select(SystemMonthlyRank).where(SystemMonthlyRank.ym == ymv).order_by(SystemMonthlyRank.rank.asc()).limit(limit)
    )).scalars().all()
    return [LeaderRow(user_id=r.user_id, rank=r.rank, score=r.score) for r in rows]

@router.get("/orgs/{org_id}", response_model=list[LeaderRow])
async def org_leaderboard(
    org_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    ym: int | None = None,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db)
):
    # Organiser must belong to the org OR user may view public org ranks (your choice; we'll require organiser for now)
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser or Service not in org")

    ymv = ym or current_ym()
    await rebuild_ranks_for_period(db, ymv)
    rows = (await db.execute(
        select(OrgMonthlyRank).where(OrgMonthlyRank.ym == ymv, OrgMonthlyRank.org_id == org_id)
        .order_by(OrgMonthlyRank.rank.asc()).limit(limit)
    )).scalars().all()
    return [LeaderRow(user_id=r.user_id, rank=r.rank, score=r.score) for r in rows]
