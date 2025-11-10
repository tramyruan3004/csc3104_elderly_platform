from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.config import get_settings
from ..models import UserPoints, PointsLedger, Rule, RuleType

settings = get_settings()

async def _get_rule_points(db: AsyncSession, org_id: uuid.UUID, rtype: RuleType) -> int:
    # prefer an active rule; otherwise default
    row = (await db.execute(
        select(Rule).where(Rule.org_id == org_id, Rule.type == rtype, Rule.active == True)
        .order_by(Rule.updated_at.desc())
    )).scalars().first()
    if row:
        return row.points
    # defaults
    if rtype == RuleType.CHECKIN:
        return settings.default_checkin_points
    return 0

async def _get_or_create_balance(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> UserPoints:
    up = (await db.execute(select(UserPoints).where(UserPoints.user_id == user_id, UserPoints.org_id == org_id))).scalar_one_or_none()
    if up:
        return up
    up = UserPoints(user_id=user_id, org_id=org_id, balance=0)
    db.add(up)
    await db.flush()
    return up

async def award_checkin_points(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    trail_id: uuid.UUID,
    details: str | None = None,
    points_override: int | None = None,
    activity_id: uuid.UUID | None = None,
    activity_order: int | None = None,
) -> int:
    pts = points_override if points_override is not None else await _get_rule_points(db, org_id, RuleType.CHECKIN)
    if pts <= 0:
        return 0
    bal = await _get_or_create_balance(db, user_id, org_id)
    reason = "activity_checkin" if activity_id else "checkin"

    detail_parts: list[str] = []
    if activity_id:
        detail_parts.append(f"activity={activity_id}")
    if activity_order is not None:
        detail_parts.append(f"order={activity_order}")
    if details:
        detail_parts.append(details)
    detail_str = ";".join(detail_parts) if detail_parts else (details or "qr-checkin")

    if activity_id:
        existing = (
            await db.execute(
                select(PointsLedger).where(
                    PointsLedger.user_id == user_id,
                    PointsLedger.org_id == org_id,
                    PointsLedger.reason == reason,
                    PointsLedger.trail_id == trail_id,
                    PointsLedger.details == detail_str,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return 0

    bal.balance += pts
    db.add(
        PointsLedger(
            user_id=user_id,
            org_id=org_id,
            delta=pts,
            reason=reason,
            trail_id=trail_id,
            details=detail_str,
        )
    )
    await db.commit()
    return pts

async def adjust_points(db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID, delta: int, reason: str, details: str | None = None) -> int:
    bal = await _get_or_create_balance(db, user_id, org_id)
    new_bal = bal.balance + delta
    if new_bal < 0:
        raise ValueError("insufficient points")
    bal.balance = new_bal
    db.add(PointsLedger(user_id=user_id, org_id=org_id, delta=delta, reason=reason, details=details))
    await db.commit()
    return bal.balance
