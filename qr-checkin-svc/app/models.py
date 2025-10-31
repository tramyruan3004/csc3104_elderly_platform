from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.types import DateTime, String

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class Checkin(Base):
    __tablename__ = "checkins"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trail_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), default="qr", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # organiser id (optional)

    __table_args__ = (
        UniqueConstraint("trail_id", "user_id", name="uq_checkin_per_user_per_trail"),
        Index("ix_checkins_trail_user", "trail_id", "user_id"),
    )
