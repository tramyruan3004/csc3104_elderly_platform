from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, declarative_base, relationship
from sqlalchemy.types import DateTime, Integer

Base = declarative_base()

class TrailStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    CANCELLED = "cancelled"

class RegStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    WAITLISTED = "waitlisted"

class Trail(Base):
    __tablename__ = "trails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TrailStatus] = mapped_column(SqlEnum(TrailStatus), default=TrailStatus.PUBLISHED, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_trails_capacity_pos"),
        CheckConstraint("ends_at > starts_at", name="ck_trails_time_range"),
        Index("ix_trails_org", "org_id"),
        Index("ix_trails_status", "status"),
        Index("ix_trails_starts", "starts_at"),
    )

    registrations: Mapped[list["Registration"]] = relationship(
        "Registration", back_populates="trail", cascade="all, delete-orphan"
    )

    activities: Mapped[list["TrailActivity"]] = relationship(
        "TrailActivity",
        back_populates="trail",
        cascade="all, delete-orphan",
        order_by="TrailActivity.order",
    )

class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trail_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trails.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    status: Mapped[RegStatus] = mapped_column(SqlEnum(RegStatus), default=RegStatus.PENDING, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("trail_id", "user_id", name="uq_registration_trail_user"), 
        Index("ix_regs_trail", "trail_id"),
        Index("ix_regs_user", "user_id"),
        Index("ix_regs_org", "org_id"),
        Index("ix_regs_status", "status"),
    )

    trail: Mapped[Trail] = relationship("Trail", back_populates="registrations")


class TrailActivity(Base):
    __tablename__ = "trail_activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trail_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trails.id", ondelete="CASCADE"), nullable=False
    )
    order: Mapped[int] = mapped_column("position", Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
    CheckConstraint("position >= 1", name="ck_trail_activity_order_pos"),
    CheckConstraint("points >= 0", name="ck_trail_activity_points_nonneg"),
    UniqueConstraint("trail_id", "position", name="uq_trail_activity_order"),
    Index("ix_trail_activity_trail_order", "trail_id", "position"),
    )

    trail: Mapped[Trail] = relationship("Trail", back_populates="activities")
