from __future__ import annotations
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class QRCreateResponse(BaseModel):
    token: str
    expires_at: int
    url: str  # convenient URL you can turn into QR (frontends just encode this)

class CheckinCreate(BaseModel):
    token: str  # signed short-TTL QR token

class CheckinRead(BaseModel):
    id: UUID
    trail_id: UUID
    org_id: UUID
    user_id: UUID
    method: str
    checked_at: datetime
    checked_by: UUID | None = None
