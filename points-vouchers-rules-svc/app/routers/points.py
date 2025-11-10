from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from ..deps import get_db, get_claims
from ..models import UserPoints, PointsLedger, Voucher, Redemption
from ..schemas import (
    BalanceRead,
    BalancePage,
    LedgerRead,
    LedgerPage,
    CheckinIngest,
    AdjustPointsRequest,
    PointsSummary,
    PointsTopUser,
    RedemptionRead,
)
from ..services.points import award_checkin_points, adjust_points

router = APIRouter(prefix="/points", tags=["points"])

def _allow_actor_for_org(claims, org_id: uuid.UUID) -> bool:
    role = claims.get("role")
    org_ids = [str(x) for x in claims.get("org_ids", [])]
    in_scope = (not org_ids) or (str(org_id) in org_ids)  # empty -> global
    return (role == "organiser" and str(org_id) in org_ids) or (role == "service" and in_scope)


def _ensure_reader_scope(claims: dict, org_id: uuid.UUID) -> None:
    role = claims.get("role")
    org_str = str(org_id)
    if role == "attend_user":
        scoped_orgs = {str(x) for x in claims.get("org_ids", []) if x}
        if not scoped_orgs:
            raise HTTPException(status_code=403, detail="Join an organisation to access rewards")
        if org_str not in scoped_orgs:
            raise HTTPException(status_code=403, detail="You are not a member of this organisation")
        return
    if role in {"organiser", "service"}:
        if not _allow_actor_for_org(claims, org_id):
            raise HTTPException(status_code=403, detail="Out of organisation scope")
        return
    if role == "admin":
        return
    raise HTTPException(status_code=403, detail="Unsupported role for this resource")


def _resolve_range(date_from: datetime | None, date_to: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = date_to or now
    start = date_from or (end - timedelta(days=30))
    if start > end:
        start, end = end, start
    return start, end

@router.get("/orgs/{org_id}/balances", response_model=BalancePage)
async def org_balances(
    org_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: uuid.UUID | None = Query(default=None),
):
    if not _allow_actor_for_org(claims, org_id) and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")

    filters = [UserPoints.org_id == org_id]
    if user_id is not None:
        filters.append(UserPoints.user_id == user_id)

    base_query = select(UserPoints).where(*filters)
    total = (await db.execute(select(func.count()).select_from(UserPoints).where(*filters))).scalar_one()

    rows = (
        await db.execute(
            base_query.order_by(UserPoints.updated_at.desc().nullslast(), UserPoints.user_id)
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    items = [
        BalanceRead(
            user_id=row.user_id,
            org_id=row.org_id,
            balance=row.balance,
            updated_at=row.updated_at,
        )
        for row in rows
    ]

    return BalancePage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )

@router.get("/orgs/{org_id}/ledger", response_model=LedgerPage)
async def org_ledger(
    org_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: uuid.UUID | None = Query(default=None),
):
    if not _allow_actor_for_org(claims, org_id) and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")

    filters = [PointsLedger.org_id == org_id]
    if user_id is not None:
        filters.append(PointsLedger.user_id == user_id)

    base_query = select(PointsLedger).where(*filters)
    total = (await db.execute(select(func.count()).select_from(PointsLedger).where(*filters))).scalar_one()

    rows = (
        await db.execute(
            base_query.order_by(PointsLedger.occurred_at.desc(), PointsLedger.user_id)
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    items = [
        LedgerRead(
            id=row.id,
            user_id=row.user_id,
            org_id=row.org_id,
            delta=row.delta,
            reason=row.reason,
            trail_id=row.trail_id,
            details=row.details,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]

    return LedgerPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/reports/orgs/{org_id}/points-summary", response_model=PointsSummary)
async def org_points_summary(
    org_id: uuid.UUID,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    if not _allow_actor_for_org(claims, org_id) and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")

    range_start, range_end = _resolve_range(date_from, date_to)
    filters = [
        PointsLedger.org_id == org_id,
        PointsLedger.occurred_at >= range_start,
        PointsLedger.occurred_at <= range_end,
    ]

    awarded_expr = func.coalesce(func.sum(case((PointsLedger.delta > 0, PointsLedger.delta), else_=0)), 0)
    redeemed_expr = func.coalesce(
        func.sum(case((PointsLedger.delta < 0, -PointsLedger.delta), else_=0)), 0
    )
    totals = (await db.execute(select(awarded_expr, redeemed_expr).where(*filters))).first()
    awarded_total = int(totals[0]) if totals else 0
    redeemed_total = int(totals[1]) if totals else 0

    top_rows = (
        await db.execute(
            select(PointsLedger.user_id, func.sum(PointsLedger.delta).label("awarded"))
            .where(*filters, PointsLedger.delta > 0)
            .group_by(PointsLedger.user_id)
            .order_by(func.sum(PointsLedger.delta).desc())
            .limit(5)
        )
    ).all()
    top_earners = [
        PointsTopUser(user_id=row.user_id, total_awarded=int(row.awarded))
        for row in top_rows
        if row.awarded
    ]

    free_redemptions = (
        await db.execute(
            select(func.count())
            .select_from(Redemption)
            .join(Voucher, Voucher.id == Redemption.voucher_id)
            .where(
                Redemption.org_id == org_id,
                Redemption.redeemed_at >= range_start,
                Redemption.redeemed_at <= range_end,
                Voucher.points_cost == 0,
            )
        )
    ).scalar_one()

    return PointsSummary(
        org_id=org_id,
        range_start=range_start,
        range_end=range_end,
        awarded_total=awarded_total,
        redeemed_total=redeemed_total,
        net_delta=awarded_total - redeemed_total,
        free_redemptions=int(free_redemptions or 0),
        top_earners=top_earners,
    )


@router.get("/reports/orgs/{org_id}/redemptions/recent", response_model=list[RedemptionRead])
async def org_recent_redemptions(
    org_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=200),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    if not _allow_actor_for_org(claims, org_id) and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")

    rows = (
        await db.execute(
            select(Redemption, Voucher)
            .join(Voucher, Voucher.id == Redemption.voucher_id)
            .where(Redemption.org_id == org_id)
            .order_by(Redemption.redeemed_at.desc())
            .limit(limit)
        )
    ).all()

    results: list[RedemptionRead] = []
    for redemption, voucher in rows:
        results.append(
            RedemptionRead(
                id=redemption.id,
                voucher_id=redemption.voucher_id,
                user_id=redemption.user_id,
                org_id=redemption.org_id,
                status=redemption.status.value,
                redeemed_at=redemption.redeemed_at,
                voucher_name=voucher.name,
                voucher_code=voucher.code,
            )
        )
    return results

@router.get("/users/me/balance", response_model=BalanceRead)
async def my_balance(org_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    _ensure_reader_scope(claims, org_id)
    user_id = uuid.UUID(claims["sub"])
    up = (await db.execute(select(UserPoints).where(UserPoints.user_id == user_id, UserPoints.org_id == org_id))).scalar_one_or_none()
    if not up:
        return BalanceRead(user_id=user_id, org_id=org_id, balance=0, updated_at=None)  # type: ignore
    return BalanceRead(user_id=up.user_id, org_id=up.org_id, balance=up.balance, updated_at=up.updated_at)

@router.get("/users/me/ledger", response_model=list[LedgerRead])
async def my_ledger(
    org_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
):
    _ensure_reader_scope(claims, org_id)
    user_id = uuid.UUID(claims["sub"])
    stmt = (
        select(PointsLedger)
        .where(PointsLedger.user_id == user_id, PointsLedger.org_id == org_id)
        .order_by(PointsLedger.occurred_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        LedgerRead(
            id=r.id,
            user_id=user_id,
            org_id=org_id,
            delta=r.delta,
            reason=r.reason,
            trail_id=r.trail_id,
            details=r.details,
            occurred_at=r.occurred_at,
        )
        for r in rows
    ]

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
        details="qr-checkin",
        points_override=payload.points_delta,
        activity_id=payload.activity_id,
        activity_order=payload.activity_order,
    )
    return {"awarded": pts}

# Manual adjust (organiser only)
@router.post("/orgs/{org_id}/adjust")
async def adjust_points_admin(
    org_id: uuid.UUID,
    payload: AdjustPointsRequest,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    reason = payload.reason.strip() if payload.reason else "manual_bonus"
    if not reason:
        reason = "manual_bonus"
    try:
        new_balance = await adjust_points(
            db,
            user_id=payload.user_id,
            org_id=org_id,
            delta=payload.delta,
            reason=reason,
        )
    except ValueError as exc:
        detail = str(exc) or "Invalid adjustment"
        if detail.lower().startswith("insufficient"):
            detail = "Insufficient points"
        raise HTTPException(status_code=400, detail=detail)
    return {"user_id": str(payload.user_id), "org_id": str(org_id), "balance": new_balance}
