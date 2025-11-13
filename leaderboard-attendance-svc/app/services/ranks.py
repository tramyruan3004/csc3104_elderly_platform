from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from collections import defaultdict
from ..models import UserMonthlyStats, OrgMonthlyRank, SystemMonthlyRank

def _now():
    return datetime.now(timezone.utc)

async def rebuild_ranks_for_period(db: AsyncSession, ym: int):
    # --- Org ranks ---
    # Collect per-org groups -> sort by checkins desc -> assign rank 1..n
    # Delete existing period rows (cheap to rebuild)
    await db.execute(delete(OrgMonthlyRank).where(OrgMonthlyRank.ym == ym))
    await db.execute(delete(SystemMonthlyRank).where(SystemMonthlyRank.ym == ym))

    # Per-org
    stats = (await db.execute(
        select(UserMonthlyStats).where(UserMonthlyStats.ym == ym, UserMonthlyStats.org_id.is_not(None))
    )).scalars().all()

    # Group by org_id and aggregate by user to avoid duplicate rank rows
    aggregated: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(lambda: defaultdict(int))
    for s in stats:
        if s.org_id is None:
            continue
        aggregated[s.org_id][s.user_id] += int(s.checkins)

    for org_id, user_scores in aggregated.items():
        sorted_rows = sorted(user_scores.items(), key=lambda item: (-item[1], str(item[0])))
        rank = 1
        for user_id, score in sorted_rows:
            db.add(OrgMonthlyRank(
                ym=ym,
                org_id=org_id,
                user_id=user_id,
                rank=rank,
                score=score,
            ))
            rank += 1

    # System-wide (org_id is NULL)
    sys_rows = (await db.execute(
        select(UserMonthlyStats).where(UserMonthlyStats.ym == ym, UserMonthlyStats.org_id.is_(None))
    )).scalars().all()

    sys_aggregated: dict[uuid.UUID, int] = defaultdict(int)
    for r in sys_rows:
        sys_aggregated[r.user_id] += int(r.checkins)

    sorted_system = sorted(sys_aggregated.items(), key=lambda item: (-item[1], str(item[0])))
    for idx, (user_id, score) in enumerate(sorted_system, start=1):
        db.add(SystemMonthlyRank(ym=ym, user_id=user_id, rank=idx, score=score))

    await db.commit()
