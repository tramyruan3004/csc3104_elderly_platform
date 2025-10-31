from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..deps import get_db, get_current_user
from ..models import UserRole, User
from ..schemas import SignUpRequest, LoginRequest, AuthResponse, TokenPair, UserRead
from ..services import auth_service
from ..core.jwks import build_rsa_jwk
from ..core.config import get_settings
from ..core.security import create_access_token
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignUpRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, access, refresh, expires_in = await auth_service.signup(
            db,
            name=payload.name,
            nric=payload.nric,
            passcode=payload.passcode,
            role=UserRole(payload.role),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    data = AuthResponse(
        user=UserRead(
            id=user.id, name=user.name, nric=user.nric, role=user.role.value, org_ids=[]
        ),
        tokens=TokenPair(access_token=access, refresh_token=refresh, expires_in=expires_in),
    )
    return data


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, access, refresh, expires_in = await auth_service.login(
            db, nric=payload.nric, passcode=payload.passcode
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # fetch org_ids through service helper
    org_ids = await auth_service._get_org_ids_for_user(db, user.id)
    return AuthResponse(
        user=UserRead(
            id=user.id, name=user.name, nric=user.nric, role=user.role.value, org_ids=org_ids
        ),
        tokens=TokenPair(access_token=access, refresh_token=refresh, expires_in=expires_in),
    )


class RefreshRequest(LoginRequest):
    pass  # we use 'refresh_token' only, leaving struct here if needed


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshBody, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        access, refresh_raw, expires_in = await auth_service.refresh(
            db, user_id=user.id, presented_refresh=body.refresh_token
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh")
    return TokenPair(access_token=access, refresh_token=refresh_raw, expires_in=expires_in)


@router.post("/logout", status_code=204)
async def logout(body: RefreshBody, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await auth_service.logout(db, user_id=user.id, presented_refresh=body.refresh_token)

@router.get("/jwks")
async def jwks():
    # keep shape compatible with JWKS consumers
    return {"keys": [build_rsa_jwk()], "alg": "RS256"}

class ServiceTokenRequest(BaseModel):
    client_id: str
    client_secret: str
    # Optional: scope the service token to certain orgs
    org_ids: list[uuid.UUID] = []
    # Optional: shorter expiry (minutes); default uses your service’s default
    expires_minutes: int | None = None

@router.post("/service-token")
async def mint_service_token(payload: ServiceTokenRequest):
    if not settings.service_client_id or not settings.service_client_secret:
        raise HTTPException(status_code=503, detail="Service credentials not configured")

    if not (payload.client_id == settings.service_client_id and payload.client_secret == settings.service_client_secret):
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    # "sub" for a service token can be a random stable UUID per client_id.
    # If you want determinism, derive a UUID5 from client_id.
    service_sub = uuid.uuid5(uuid.NAMESPACE_DNS, f"service:{payload.client_id}")

    access = create_access_token(
        user_id=service_sub,
        role="service",
        org_ids=payload.org_ids,                 # scope to certain orgs, or leave []
        expires_minutes=payload.expires_minutes  # optional
    )
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": (payload.expires_minutes or 15) * 60
    }