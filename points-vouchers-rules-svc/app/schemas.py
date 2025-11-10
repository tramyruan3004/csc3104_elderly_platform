from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime

PosInt     = Annotated[int, Field(gt=0)]
NonNegInt  = Annotated[int, Field(ge=0)]
Name128    = Annotated[str, Field(min_length=1, max_length=128)]
Code64     = Annotated[str, Field(min_length=3, max_length=64)]

OptStr     = str | None

# --- points
class BalanceRead(BaseModel):
    user_id: UUID
    org_id: UUID
    balance: int
    updated_at: datetime | None = None


class BalancePage(BaseModel):
    items: list[BalanceRead]
    total: int
    limit: int
    offset: int
    has_more: bool

class LedgerRead(BaseModel):
    id: UUID
    user_id: UUID
    org_id: UUID
    delta: int
    reason: str
    trail_id: UUID | None = None
    details: str | None = None
    occurred_at: datetime


class LedgerPage(BaseModel):
    items: list[LedgerRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class AdjustPointsRequest(BaseModel):
    user_id: UUID
    delta: int
    reason: str | None = Field(default=None, max_length=64)

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must not be zero")
        return value

# --- rules
class RuleCreate(BaseModel):
    type: Literal["checkin", "manual_bonus"]
    points: PosInt
    name: Name128
    description: OptStr = None
    active: bool = True

class RuleUpdate(BaseModel):
    points: PosInt | None = None
    name: Name128 | None = None
    description: OptStr = None
    active: bool | None = None

class RuleRead(BaseModel):
    id: UUID
    org_id: UUID
    type: Literal["checkin", "manual_bonus"]
    points: int
    name: str
    description: OptStr
    active: bool

# --- vouchers
class VoucherCreate(BaseModel):
    code: Code64
    name: Name128
    points_cost: NonNegInt
    total_quantity: PosInt | None = None  # None = unlimited

class VoucherUpdate(BaseModel):
    name: Name128 | None = None
    points_cost: NonNegInt | None = None
    status: Literal["active", "disabled"] | None = None
    total_quantity: PosInt | None = None

class VoucherRead(BaseModel):
    id: UUID
    org_id: UUID
    code: str
    name: str
    points_cost: int
    status: Literal["active", "disabled"]
    total_quantity: int | None
    redeemed_count: int

class RedemptionRead(BaseModel):
    id: UUID
    voucher_id: UUID
    user_id: UUID
    org_id: UUID
    status: Literal["redeemed", "voided", "cancelled"] | str  # adjust to your enums
    redeemed_at: datetime
    voucher_name: str | None = None
    voucher_code: str | None = None

# --- ingest (from qr-checkin-svc)
class CheckinIngest(BaseModel):
    trail_id: UUID
    user_id: UUID
    org_id: UUID
    checked_at: datetime
    activity_id: UUID | None = None
    activity_order: int | None = Field(default=None, ge=1)
    points_delta: int | None = None
    new_attendance: bool | None = None


class PointsTopUser(BaseModel):
    user_id: UUID
    total_awarded: int


class PointsSummary(BaseModel):
    org_id: UUID
    range_start: datetime
    range_end: datetime
    awarded_total: int
    redeemed_total: int
    net_delta: int
    free_redemptions: int
    top_earners: list[PointsTopUser] = Field(default_factory=list)
