from __future__ import annotations
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class QRCreateResponse(BaseModel):
    token: str
    expires_at: int
    url: str  
    activity_id: UUID | None = None
    activity_order: int | None = Field(default=None, ge=1)
    points: int | None = Field(default=None, ge=0)

class CheckinCreate(BaseModel):
    token: str  # signed short-TTL QR token
    activity_id: UUID | None = None
    activity_order: int | None = Field(default=None, ge=1)
    points: int | None = Field(default=None, ge=0)


class QRActivityCreate(BaseModel):
    activity_order: int | None = Field(default=None, ge=1)
    points: int | None = Field(default=None, ge=0)

class CheckinRead(BaseModel):
    id: UUID
    trail_id: UUID
    org_id: UUID
    user_id: UUID
    method: str
    checked_at: datetime
    checked_by: UUID | None = None
    activity_id: UUID | None = None
    activity_order: int | None = None
    points_awarded: int | None = None
    new_attendance: bool | None = None
    new_activity: bool | None = None
