from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
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

    # Group by org_id
    from collections import defaultdict
    by_org: dict[uuid.UUID, list[UserMonthlyStats]] = defaultdict(list)
    for s in stats:
        by_org[s.org_id].append(s)  # type: ignore[arg-type]

    for org_id, rows in by_org.items():
        # sort by checkins desc; tiebreaker by user_id for stability
        rows.sort(key=lambda r: (-int(r.checkins), str(r.user_id)))
        for idx, r in enumerate(rows, start=1):
            db.add(OrgMonthlyRank(
                ym=ym, org_id=org_id, user_id=r.user_id, rank=idx, score=int(r.checkins)
            ))

    # System-wide
    sys_rows = (await db.execute(
        select(UserMonthlyStats).where(UserMonthlyStats.ym == ym, UserMonthlyStats.org_id.is_(None))
    )).scalars().all()
    sys_rows.sort(key=lambda r: (-int(r.checkins), str(r.user_id)))
    for idx, r in enumerate(sys_rows, start=1):
        db.add(SystemMonthlyRank(ym=ym, user_id=r.user_id, rank=idx, score=int(r.checkins)))

    await db.commit()
