from __future__ import annotations
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

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
