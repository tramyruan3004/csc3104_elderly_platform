from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_current_user
from ..models import OrgMember, User
from ..schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(OrgMember.org_id).where(OrgMember.user_id == user.id))
    org_ids = [r[0] for r in rows.all()]
    return UserRead(id=user.id, name=user.name, nric=user.nric, role=user.role.value, org_ids=org_ids)