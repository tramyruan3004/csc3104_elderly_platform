from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_claims
from ..models import Voucher, VoucherStatus, Redemption, UserPoints, PointsLedger
from ..schemas import VoucherCreate, VoucherUpdate, VoucherRead, RedemptionRead

router = APIRouter(prefix="/vouchers", tags=["vouchers"])

def _allow_actor_for_org(claims, org_id: uuid.UUID) -> bool:
    role = claims.get("role")
    org_ids = [str(x) for x in claims.get("org_ids", [])]
    in_scope = (not org_ids) or (str(org_id) in org_ids)  # empty -> global
    return (role == "organiser" and str(org_id) in org_ids) or (role == "service" and in_scope)


def _ensure_view_scope(claims: dict, org_id: uuid.UUID) -> None:
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

@router.get("", response_model=list[VoucherRead])
async def list_vouchers(
    org_id: uuid.UUID = Query(...),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    _ensure_view_scope(claims, org_id)
    stmt = select(Voucher).where(Voucher.org_id == org_id)
    if claims.get("role") == "attend_user":
        stmt = stmt.where(Voucher.status == VoucherStatus.ACTIVE)
    rows = (await db.execute(stmt.order_by(Voucher.points_cost.asc(), Voucher.name.asc()))).scalars().all()
    return [VoucherRead(
        id=v.id, org_id=v.org_id, code=v.code, name=v.name, points_cost=v.points_cost,
        status=v.status.value, total_quantity=v.total_quantity, redeemed_count=v.redeemed_count
    ) for v in rows]

@router.post("/orgs/{org_id}", response_model=VoucherRead, status_code=201)
async def create_voucher(org_id: uuid.UUID, payload: VoucherCreate, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    v = Voucher(org_id=org_id, code=payload.code, name=payload.name, points_cost=payload.points_cost, total_quantity=payload.total_quantity)
    db.add(v); await db.commit(); await db.refresh(v)
    return VoucherRead(id=v.id, org_id=v.org_id, code=v.code, name=v.name, points_cost=v.points_cost, status=v.status.value, total_quantity=v.total_quantity, redeemed_count=v.redeemed_count)

@router.patch("/{voucher_id}", response_model=VoucherRead)
async def update_voucher(voucher_id: uuid.UUID, payload: VoucherUpdate, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    v = (await db.execute(select(Voucher).where(Voucher.id == voucher_id))).scalar_one_or_none()
    if not v: raise HTTPException(status_code=404, detail="Voucher not found")
    if not _allow_actor_for_org(claims, v.org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    if payload.name is not None: v.name = payload.name
    if payload.points_cost is not None: v.points_cost = payload.points_cost
    if payload.status is not None:
        v.status = VoucherStatus(payload.status)
    if payload.total_quantity is not None: v.total_quantity = payload.total_quantity
    await db.commit(); await db.refresh(v)
    return VoucherRead(id=v.id, org_id=v.org_id, code=v.code, name=v.name, points_cost=v.points_cost, status=v.status.value, total_quantity=v.total_quantity, redeemed_count=v.redeemed_count)

@router.post("/{voucher_id}/redeem", response_model=RedemptionRead, status_code=201)
async def redeem_voucher(voucher_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    v = (await db.execute(select(Voucher).where(Voucher.id == voucher_id))).scalar_one_or_none()
    if not v: raise HTTPException(status_code=404, detail="Voucher not found")
    _ensure_view_scope(claims, v.org_id)
    if v.status != VoucherStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Voucher not active")
    if v.total_quantity is not None and v.redeemed_count >= v.total_quantity:
        raise HTTPException(status_code=409, detail="Voucher exhausted")

    up = None
    if v.points_cost > 0:
        up = (await db.execute(select(UserPoints).where(UserPoints.user_id == user_id, UserPoints.org_id == v.org_id))).scalar_one_or_none()
        if not up or up.balance < v.points_cost:
            raise HTTPException(status_code=400, detail="Insufficient points")
        up.balance -= v.points_cost
    red = Redemption(voucher_id=v.id, user_id=user_id, org_id=v.org_id)
    v.redeemed_count += 1
    db.add(red)
    if v.points_cost > 0:
        db.add(PointsLedger(user_id=user_id, org_id=v.org_id, delta=-v.points_cost, reason="voucher_redeem", details=f"voucher:{v.code}"))
    await db.commit(); await db.refresh(v); await db.refresh(red)
    return RedemptionRead(
        id=red.id,
        voucher_id=red.voucher_id,
        user_id=red.user_id,
        org_id=red.org_id,
        status=red.status.value,
        redeemed_at=red.redeemed_at,
        voucher_name=v.name,
        voucher_code=v.code,
        points_cost=v.points_cost,
    )

@router.get("/users/me/redemptions", response_model=list[RedemptionRead])
async def my_redemptions(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    user_id = uuid.UUID(claims["sub"])
    rows = (
        await db.execute(
            select(Redemption, Voucher)
            .join(Voucher, Voucher.id == Redemption.voucher_id)
            .where(Redemption.user_id == user_id)
            .order_by(Redemption.redeemed_at.desc())
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
                points_cost=voucher.points_cost,
            )
        )
    return results
