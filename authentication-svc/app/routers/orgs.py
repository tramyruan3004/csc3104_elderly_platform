from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import uuid

from ..deps import get_db, require_organiser
from ..models import Organization, OrgMember, User, UserRole
from ..schemas import OrganizationCreate, OrganizationRead, AddMemberRequest

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.post("", response_model=OrganizationRead)
async def create_org(payload: OrganizationCreate, actor: User = Depends(require_organiser), db: AsyncSession = Depends(get_db)):
    # ensure unique name
    exists = (await db.execute(select(Organization.id).where(Organization.name == payload.name))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization name already exists")

    org = Organization(id=uuid.uuid4(), name=payload.name)
    db.add(org)
    await db.commit()
    return OrganizationRead(id=org.id, name=org.name)


@router.post("/{org_id}/members", status_code=204)
async def add_member(org_id: uuid.UUID, body: AddMemberRequest, actor: User = Depends(require_organiser), db: AsyncSession = Depends(get_db)):
    # (optional) require actor to be a member of the org they modify — enable if needed:
    # is_member = (await db.execute(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == actor.id))).scalar_one_or_none()
    # if not is_member:
    #     raise HTTPException(status_code=403, detail="Not a member of this org")

    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    target: User | None = None
    if body.user_id:
        target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    elif body.nric:
        target = (await db.execute(select(User).where(User.nric == body.nric))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    if target.role != UserRole.ORGANISER:
        raise HTTPException(status_code=400, detail="Only organisers can be org members")

    # upsert-ish: respect uniqueness
    existing = (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == target.id)
    )).scalar_one_or_none()
    if existing:
        return  # 204

    db.add(OrgMember(org_id=org_id, user_id=target.id, role_in_org=UserRole.ORGANISER))
    await db.commit()


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member(org_id: uuid.UUID, user_id: uuid.UUID, actor: User = Depends(require_organiser), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id))
    await db.commit()
