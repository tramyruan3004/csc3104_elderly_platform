from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
import uuid

from ..deps import get_db, require_organiser, require_active_user, require_attendee
from ..models import Organization, OrgMember, User, UserRole
from ..schemas import OrganizationCreate, OrganizationRead, AddMemberRequest, OrganizationStats

router = APIRouter(prefix="/orgs", tags=["organizations"])


# Provide a simple list endpoint so organisers can see available organisations.
@router.get("", response_model=list[OrganizationRead])
async def list_orgs(user: User = Depends(require_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization).order_by(Organization.name))
    organizations = result.scalars().all()
    return [OrganizationRead(id=org.id, name=org.name) for org in organizations]


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

    if target.role not in (UserRole.ORGANISER, UserRole.ATTEND_USER):
        raise HTTPException(status_code=400, detail="User role is not eligible for organisation membership")

    # upsert-ish: respect uniqueness
    existing = (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == target.id)
    )).scalar_one_or_none()
    if existing:
        return  # 204

    db.add(OrgMember(org_id=org_id, user_id=target.id, role_in_org=target.role))
    await db.commit()


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member(org_id: uuid.UUID, user_id: uuid.UUID, actor: User = Depends(require_organiser), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id))
    await db.commit()


@router.post("/{org_id}/self-join", response_model=OrganizationRead, status_code=200)
async def self_join_org(
    org_id: uuid.UUID,
    actor: User = Depends(require_attendee),
    db: AsyncSession = Depends(get_db),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = (
        await db.execute(
            select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == actor.id)
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(OrgMember(org_id=org_id, user_id=actor.id, role_in_org=UserRole.ATTEND_USER))
        await db.commit()
    return OrganizationRead(id=org.id, name=org.name)


@router.get("/{org_id}/stats", response_model=OrganizationStats)
async def org_stats(
    org_id: uuid.UUID,
    actor: User = Depends(require_organiser),
    db: AsyncSession = Depends(get_db),
):
    membership = (
        await db.execute(
            select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == actor.id)
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organisation")

    organiser_count = (
        await db.execute(
            select(func.count()).select_from(OrgMember).where(
                OrgMember.org_id == org_id, OrgMember.role_in_org == UserRole.ORGANISER
            )
        )
    ).scalar_one()
    attendee_count = (
        await db.execute(
            select(func.count()).select_from(OrgMember).where(
                OrgMember.org_id == org_id, OrgMember.role_in_org == UserRole.ATTEND_USER
            )
        )
    ).scalar_one()
    total = organiser_count + attendee_count
    return OrganizationStats(
        org_id=org_id,
        organisers=int(organiser_count),
        attendees=int(attendee_count),
        total_members=int(total),
    )
