from __future__ import annotations
from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

Str255     = Annotated[str, Field(min_length=1, max_length=255)]
OptStr255  = Annotated[str | None, Field(max_length=255)]
PosInt     = Annotated[int, Field(gt=0)]

# ---- Trails ----
class TrailCreate(BaseModel):
    title: Str255
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    location: OptStr255 = None
    capacity: PosInt

    @model_validator(mode="after")
    def _check_dates(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self

class TrailUpdate(BaseModel):
    title: Str255 | None = None
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: OptStr255 = None
    capacity: PosInt | None = None
    status: Literal["draft", "published", "closed", "cancelled"] | None = None

class TrailRead(BaseModel):
    id: UUID
    org_id: UUID
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    capacity: int
    status: Literal["draft", "published", "closed", "cancelled"]

# ---- Registrations ----
class RegistrationCreateSelf(BaseModel):
    note: str | None = None

class RegistrationCreateByOrganiser(BaseModel):
    user_id: UUID
    note: str | None = None

class RegistrationRead(BaseModel):
    id: UUID
    trail_id: UUID
    user_id: UUID
    org_id: UUID
    status: Literal["pending", "approved", "rejected", "cancelled"] | str  # adjust as needed
    note: str | None = None