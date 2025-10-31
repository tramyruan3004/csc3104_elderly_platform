from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import UniqueConstraint, Index, Integer, String, BigInteger, Boolean
from sqlalchemy.types import DateTime

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

def ym_from_dt(dt: datetime) -> int:
    # YYYYMM as int
    return dt.year * 100 + dt.month

# Raw attendance row (ingested from NATS)
class Attendance(Base):
    __tablename__ = "attendance"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trail_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # unique per trail+user to keep idempotency
    __table_args__ = (UniqueConstraint("trail_id", "user_id", name="uq_attendance_trail_user"),)

# Monthly per-user stats (both per-org and system-wide)
# We store two rows per checkin: one with real org_id, one with system row marked by org_id = NULL
class UserMonthlyStats(Base):
    __tablename__ = "user_monthly_stats"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ym: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # YYYYMM
    org_id: Mapped[uuid.UUID | None] = mapped_column(index=True, nullable=True)  # None => system-wide
    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    # metrics
    checkins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("ym", "org_id", "user_id", name="uq_stats_period_scope"),
        Index("ix_stats_scope", "ym", "org_id", "checkins"),
    )

# Materialised rank tables (fast read)
class OrgMonthlyRank(Base):
    __tablename__ = "org_monthly_rank"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ym: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # checkins (for now)
    # simple rebuild cadence
    rebuilt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("ym", "org_id", "user_id", name="uq_org_rank_row"),)

class SystemMonthlyRank(Base):
    __tablename__ = "system_monthly_rank"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ym: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    rebuilt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("ym", "user_id", name="uq_system_rank_row"),)
