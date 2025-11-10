from __future__ import annotations
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime, date

class LeaderRow(BaseModel):
    user_id: UUID
    rank: int
    score: int

class AttendanceRow(BaseModel):
    id: UUID
    trail_id: UUID
    org_id: UUID
    user_id: UUID
    checked_at: datetime


class AttendanceTrailSummary(BaseModel):
    trail_id: UUID
    checkins: int
    unique_participants: int


class AttendanceDailySummary(BaseModel):
    day: date
    checkins: int


class AttendanceSummary(BaseModel):
    org_id: UUID
    range_start: datetime
    range_end: datetime
    total_checkins: int
    unique_participants: int
    last_checkin_at: datetime | None = None
    per_trail: list[AttendanceTrailSummary] = Field(default_factory=list)
    daily: list[AttendanceDailySummary] = Field(default_factory=list)
