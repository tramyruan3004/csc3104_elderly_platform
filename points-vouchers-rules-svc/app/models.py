from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    UniqueConstraint, Index, CheckConstraint, String, Text, Integer, Enum as SqlEnum, ForeignKey
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, Numeric

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class RuleType(str, Enum):
    CHECKIN = "checkin"           # award points on check-in
    MANUAL_BONUS = "manual_bonus" # organiser grants

class VoucherStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"

class RedemptionStatus(str, Enum):
    RESERVED = "reserved"   # optional stage
    REDEEMED = "redeemed"
    CANCELLED = "cancelled"

class UserPoints(Base):
    __tablename__ = "user_points"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_user_org_balance"),
        Index("ix_points_user", "user_id"),
        Index("ix_points_org", "org_id"),
    )

class PointsLedger(Base):
    __tablename__ = "points_ledger"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)  # + or -
    reason: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., "checkin", "voucher_redeem", "manual"
    trail_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_ledger_user", "user_id"),
        Index("ix_ledger_org", "org_id"),
        Index("ix_ledger_reason", "reason"),
    )

class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    type: Mapped[RuleType] = mapped_column(SqlEnum(RuleType), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_rules_org", "org_id"),
        Index("ix_rules_type", "type"),
    )

class Voucher(Base):
    __tablename__ = "vouchers"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    points_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VoucherStatus] = mapped_column(SqlEnum(VoucherStatus), default=VoucherStatus.ACTIVE, nullable=False)
    total_quantity: Mapped[int | None] = mapped_column(Integer)  # null = unlimited
    redeemed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("points_cost > 0", name="ck_voucher_cost"),
        Index("ix_vouchers_org", "org_id"),
        Index("ix_vouchers_code", "code"),
    )

class Redemption(Base):
    __tablename__ = "redemptions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    voucher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vouchers.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    status: Mapped[RedemptionStatus] = mapped_column(SqlEnum(RedemptionStatus), default=RedemptionStatus.REDEEMED, nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    voucher: Mapped[Voucher] = relationship("Voucher")

    __table_args__ = (
        Index("ix_redemptions_user", "user_id"),
        Index("ix_redemptions_org", "org_id"),
        Index("ix_redemptions_voucher", "voucher_id"),
    )
