from __future__ import annotations
from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

Str255     = Annotated[str, Field(min_length=1, max_length=255)]
OptStr255  = Annotated[str | None, Field(max_length=255)]
PosInt     = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]

# ---- Trails ----
class TrailCreate(BaseModel):
    title: Str255
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    location: OptStr255 = None
    capacity: PosInt
    status: Literal["draft", "published", "closed", "cancelled"] | None = "published"

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
    created_by: UUID
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    capacity: int
    status: Literal["draft", "published", "closed", "cancelled"]
    created_at: datetime
    updated_at: datetime

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
    status: Literal["pending", "approved", "confirmed", "rejected", "cancelled", "waitlisted"] | str
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class UpcomingTrailSummary(BaseModel):
    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    capacity: int
    confirmed_registrations: int


class TrailsOverview(BaseModel):
    org_id: UUID
    total_trails: int
    draft: int
    published: int
    closed: int
    cancelled: int
    total_capacity: int
    confirmed_registrations: int
    upcoming: list[UpcomingTrailSummary] = Field(default_factory=list)


class TrailActivityBase(BaseModel):
    title: Str255
    points: NonNegativeInt = 0
    notes: OptStr255 = None


class TrailActivityCreate(TrailActivityBase):
    order: Annotated[int | None, Field(ge=1)] = None


class TrailActivityUpdate(BaseModel):
    title: Str255 | None = None
    points: NonNegativeInt | None = None
    notes: OptStr255 = None
    order: Annotated[int | None, Field(ge=1)] = None


class TrailActivityRead(BaseModel):
    id: UUID
    trail_id: UUID
    title: str
    points: int
    notes: str | None
    order: int
    created_at: datetime
    updated_at: datetime
