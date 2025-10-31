from __future__ import annotations

from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, Field, constr

Str255   = Annotated[str, Field(strip_whitespace=True, min_length=1, max_length=255)]
NRICType = Annotated[str, Field(strip_whitespace=True, min_length=3, max_length=32)]
Passcode8 = Annotated[str, Field(pattern=r"^\d{8}$")]  # ddmmyyyy

# -------- Auth --------
class SignUpRequest(BaseModel):
    name: Str255
    nric: NRICType
    passcode: Passcode8
    role: Literal["attend_user", "organiser"]


class LoginRequest(BaseModel):
    nric: NRICType
    passcode: Passcode8


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


# -------- Users --------
class UserRead(BaseModel):
    id: UUID
    name: str
    nric: str
    role: Literal["attend_user", "organiser"]
    org_ids: list[UUID] = Field(default_factory=list)


class AuthResponse(BaseModel):
    user: UserRead
    tokens: TokenPair


# -------- Orgs --------
class OrganizationCreate(BaseModel):
    name: Str255


class OrganizationRead(BaseModel):
    id: UUID
    name: str


class AddMemberRequest(BaseModel):
    nric: str | None = None
    user_id: UUID | None = None