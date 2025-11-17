from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple, List
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Credential, RefreshToken, UserRole, OrgMember
from ..core.security import (
    hash_passcode,
    verify_passcode,
    hash_password,
    verify_password,
    create_token_pair,
)
import uuid
from ..core.config import get_settings

settings = get_settings()


async def _get_org_ids_for_user(db: AsyncSession, user_id: UUID) -> List[UUID]:
    rows = await db.execute(select(OrgMember.org_id).where(OrgMember.user_id == user_id))
    return [r[0] for r in rows.all()]


async def signup(
    db: AsyncSession,
    *,
    name: str,
    nric: str,
    passcode: str,
    role: UserRole,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> Tuple[User, str, str, int]:
    # ensure unique NRIC
    exists = (await db.execute(select(User.id).where(User.nric == nric))).scalar_one_or_none()
    if exists:
        raise ValueError("NRIC already registered")

    if admin_username:
        existing_admin = (
            await db.execute(select(Credential).where(Credential.admin_username == admin_username))
        ).scalar_one_or_none()
        if existing_admin:
            raise ValueError("Admin username already in use")

    if admin_username or admin_password:
        if role not in (UserRole.ORGANISER, UserRole.ADMIN):
            raise ValueError("Admin credentials can only be attached to organiser or admin roles")
        if not admin_username or not admin_password:
            raise ValueError("Both admin username and password are required")

    user = User(
        id=uuid.uuid4(),
        name=name,
        nric=nric,
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # get user.id

    cred = Credential(user_id=user.id, passcode_hash=hash_passcode(passcode))
    if admin_username and admin_password:
        cred.admin_username = admin_username
        cred.admin_password_hash = hash_password(admin_password)
    db.add(cred)
    await db.commit()

    org_ids = await _get_org_ids_for_user(db, user.id)
    access, refresh_raw, expires_in, refresh_hash = create_token_pair(
        user_id=user.id, role=user.role.value, org_ids=org_ids
    )
    # persist refresh
    rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_exp_minutes),
        revoked=False,
    )
    db.add(rt)
    await db.commit()

    return user, access, refresh_raw, expires_in


async def login(db: AsyncSession, *, nric: str, passcode: str) -> Tuple[User, str, str, int]:
    user = (await db.execute(select(User).where(User.nric == nric))).scalar_one_or_none()
    if not user or not user.is_active:
        raise PermissionError("Invalid credentials")

    cred = (await db.execute(select(Credential).where(Credential.user_id == user.id))).scalar_one_or_none()
    if not cred or not verify_passcode(passcode, cred.passcode_hash):
        raise PermissionError("Invalid credentials")

    org_ids = await _get_org_ids_for_user(db, user.id)
    access, refresh_raw, expires_in, refresh_hash = create_token_pair(
        user_id=user.id, role=user.role.value, org_ids=org_ids
    )
    rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_exp_minutes),
        revoked=False,
    )
    db.add(rt)
    await db.commit()
    return user, access, refresh_raw, expires_in


async def admin_login(db: AsyncSession, *, username: str, password: str) -> Tuple[User, str, str, int]:
    cred = (
        await db.execute(select(Credential).where(Credential.admin_username == username))
    ).scalar_one_or_none()
    if not cred or not cred.admin_password_hash:
        raise PermissionError("Invalid credentials")

    if not verify_password(password, cred.admin_password_hash):
        raise PermissionError("Invalid credentials")

    user = (
        await db.execute(select(User).where(User.id == cred.user_id))
    ).scalar_one_or_none()

    if not user or not user.is_active or user.role not in (UserRole.ORGANISER, UserRole.ADMIN):
        raise PermissionError("Invalid credentials")

    org_ids = await _get_org_ids_for_user(db, user.id)
    access, refresh_raw, expires_in, refresh_hash = create_token_pair(
        user_id=user.id, role=user.role.value, org_ids=org_ids
    )
    rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_exp_minutes),
        revoked=False,
    )
    db.add(rt)
    await db.commit()
    return user, access, refresh_raw, expires_in


async def refresh(db: AsyncSession, *, user_id: UUID, presented_refresh: str) -> Tuple[str, str, int]:
    import hashlib
    token_hash = hashlib.sha256(presented_refresh.encode("utf-8")).hexdigest()

    rt = (await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.token_hash == token_hash, RefreshToken.revoked == False)
    )).scalar_one_or_none()
    if not rt or rt.expires_at <= datetime.now(timezone.utc):
        raise PermissionError("Invalid refresh")

    rt.revoked = True

    org_ids = await _get_org_ids_for_user(db, user_id)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    access, refresh_raw, expires_in, refresh_hash = create_token_pair(
        user_id=user_id, role=user.role.value, org_ids=org_ids
    )
    new_rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_exp_minutes),
        revoked=False,
    )
    db.add(new_rt)
    await db.commit()
    return access, refresh_raw, expires_in


async def logout(db: AsyncSession, *, user_id: UUID, presented_refresh: str) -> None:
    import hashlib
    token_hash = hashlib.sha256(presented_refresh.encode("utf-8")).hexdigest()
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.token_hash == token_hash)
    )
    await db.commit()
