from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_current_user, require_organiser
from ..models import OrgMember, User, UserRole
from ..schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(OrgMember.org_id).where(OrgMember.user_id == user.id))
    org_ids = [r[0] for r in rows.all()]
    return UserRead(id=user.id, name=user.name, nric=user.nric, role=user.role.value, org_ids=org_ids)


@router.get("/lookup", response_model=UserRead)
async def lookup_by_nric(
    nric: str = Query(..., min_length=3, max_length=32,
                      description="NRIC identifier of the participant"),
    actor: User = Depends(require_organiser),
    db: AsyncSession = Depends(get_db),
):
    lookup_result = await db.execute(select(User).where(User.nric == nric))
    target = lookup_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.role != UserRole.ATTEND_USER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NRIC does not belong to a participant")
    if not target.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is inactive")

    org_rows = await db.execute(select(OrgMember.org_id).where(OrgMember.user_id == target.id))
    org_ids = [r[0] for r in org_rows.all()]
    return UserRead(
        id=target.id,
        name=target.name,
        nric=target.nric,
        role=target.role.value,
        org_ids=org_ids,
    )


@router.get("/participants", response_model=list[UserRead])
async def list_participants(actor: User = Depends(require_organiser), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.role == UserRole.ATTEND_USER).order_by(User.name)
    )
    users = result.scalars().all()
    if not users:
        return []

    user_ids = [user.id for user in users]
    membership_rows = await db.execute(
        select(OrgMember.user_id, OrgMember.org_id).where(OrgMember.user_id.in_(user_ids))
    )
    membership_map: dict = {}
    for user_id, org_id in membership_rows.all():
        membership_map.setdefault(user_id, []).append(org_id)

    return [
        UserRead(
            id=user.id,
            name=user.name,
            nric=user.nric,
            role=user.role.value,
            org_ids=membership_map.get(user.id, []),
        )
        for user in users
    ]