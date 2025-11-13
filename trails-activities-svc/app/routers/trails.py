# app/routers/trails.py  (REPLACE FILE)
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from ..deps import get_db, get_claims
from ..models import Trail, TrailStatus, Registration, RegStatus, TrailActivity
from ..schemas import (
    TrailCreate,
    TrailUpdate,
    TrailRead,
    TrailsOverview,
    UpcomingTrailSummary,
    TrailActivityCreate,
    TrailActivityUpdate,
    TrailActivityRead,
)

router = APIRouter(prefix="/trails", tags=["trails"])

def _ensure_organiser_for_org(claims, org_id: uuid.UUID):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organiser role required")
    if str(org_id) not in [str(x) for x in claims.get("org_ids", [])]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")


def _ensure_report_scope(claims, org_id: uuid.UUID):
    role = claims.get("role")
    scoped_orgs = {str(x) for x in claims.get("org_ids", []) if x}
    if role == "organiser":
        if str(org_id) not in scoped_orgs:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organisation")
        return
    if role == "service":
        if scoped_orgs and str(org_id) not in scoped_orgs:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service token not scoped for organisation")
        return
    if role == "admin":
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reporting scope not allowed for role")


async def _fetch_trail(db: AsyncSession, trail_id: uuid.UUID) -> Trail | None:
    return (
        await db.execute(select(Trail).where(Trail.id == trail_id))
    ).scalar_one_or_none()


async def _require_trail_for_organiser(
    db: AsyncSession, trail_id: uuid.UUID, claims: dict
) -> Trail:
    trail = await _fetch_trail(db, trail_id)
    if not trail:
        raise HTTPException(status_code=404, detail="Trail not found")
    _ensure_organiser_for_org(claims, trail.org_id)
    return trail


def _activity_to_schema(entity: TrailActivity) -> TrailActivityRead:
    return TrailActivityRead(
        id=entity.id,
        trail_id=entity.trail_id,
        title=entity.title,
        points=entity.points,
        notes=entity.notes,
        order=entity.order,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )

@router.get("", response_model=list[TrailRead])
async def list_trails(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID | None = Query(default=None),
    status_filter: TrailStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    claims: dict = Depends(get_claims),
):
    role = claims.get("role")
    if role not in {"attend_user", "organiser", "service", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized role")

    claim_org_ids = [uuid.UUID(str(oid)) for oid in claims.get("org_ids", []) if oid]

    allowed_org_ids: list[uuid.UUID] | None = None
    status_set: set[TrailStatus] | None = None

    if role == "attend_user":
        if not claim_org_ids:
            # attendee without org membership should see nothing
            return []
        if org_id:
            if org_id not in claim_org_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not part of organisation")
            allowed_org_ids = [org_id]
        else:
            allowed_org_ids = claim_org_ids
        attendee_allowed_statuses = {TrailStatus.PUBLISHED, TrailStatus.CLOSED}
        if status_filter:
            if status_filter not in attendee_allowed_statuses:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Attendee cannot view that status")
            status_set = {status_filter}
        else:
            status_set = attendee_allowed_statuses
    elif role == "organiser":
        if org_id:
            _ensure_organiser_for_org(claims, org_id)
            allowed_org_ids = [org_id]
        elif claim_org_ids:
            allowed_org_ids = claim_org_ids
        if status_filter:
            status_set = {status_filter}
    elif role == "service":
        if org_id:
            if claim_org_ids and org_id not in claim_org_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service token not scoped for org")
            allowed_org_ids = [org_id]
        elif claim_org_ids:
            allowed_org_ids = claim_org_ids
        if status_filter:
            status_set = {status_filter}
    else:  # admin
        if org_id:
            allowed_org_ids = [org_id]
        if status_filter:
            status_set = {status_filter}

    stmt = select(Trail)
    if allowed_org_ids is not None:
        if not allowed_org_ids:
            return []
        stmt = stmt.where(Trail.org_id.in_(allowed_org_ids))
    if status_set is not None:
        stmt = stmt.where(Trail.status.in_(status_set))
    if date_from:
        stmt = stmt.where(Trail.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Trail.starts_at < date_to)

    rows = (await db.execute(stmt.order_by(Trail.starts_at.asc()))).scalars().all()
    return [
        TrailRead(
            id=t.id,
            org_id=t.org_id,
            created_by=t.created_by,
            title=t.title,
            description=t.description,
            starts_at=t.starts_at,
            ends_at=t.ends_at,
            location=t.location,
            capacity=t.capacity,
            status=t.status.value,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in rows
    ]

@router.get("/{trail_id}", response_model=TrailRead)
async def get_trail(trail_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    t = await _fetch_trail(db, trail_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")
    return TrailRead(
        id=t.id,
        org_id=t.org_id,
        title=t.title,
        description=t.description,
        starts_at=t.starts_at,
        ends_at=t.ends_at,
        location=t.location,
        capacity=t.capacity,
        status=t.status.value,
        created_by=t.created_by,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )

@router.get("/{trail_id}/attendees")
async def list_attendees(
    trail_id: uuid.UUID,
    status_filter: RegStatus | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: Literal["created", "updated"] = Query(default="created"),
    direction: Literal["asc", "desc"] = Query(default="asc"),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    await _require_trail_for_organiser(db, trail_id, claims)

    base_q = select(Registration).where(Registration.trail_id == trail_id)
    if status_filter:
        base_q = base_q.where(Registration.status == status_filter)

    total_stmt = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    column = Registration.created_at if sort == "created" else Registration.updated_at
    ordering = column.asc() if direction == "asc" else column.desc()
    query = base_q.order_by(ordering, Registration.created_at.asc(), Registration.id.asc())
    if limit is not None:
        query = query.limit(limit).offset(offset)
    regs = (await db.execute(query)).scalars().all()

    items = [
        {
            "registration_id": r.id,
            "id": r.id,
            "trail_id": r.trail_id,
            "org_id": r.org_id,
            "user_id": r.user_id,
            "status": r.status.value,
            "note": r.note,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in regs
    ]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(items)) < total,
    }

@router.post("/orgs/{org_id}", response_model=TrailRead, status_code=201)
async def create_trail(
    org_id: uuid.UUID,
    payload: TrailCreate,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    _ensure_organiser_for_org(claims, org_id)
    t = Trail(
        org_id=org_id,
        title=payload.title,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        location=payload.location,
        capacity=payload.capacity,
        status=TrailStatus(payload.status) if payload.status else TrailStatus.PUBLISHED,
        created_by=uuid.UUID(claims["sub"]),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return TrailRead(
        id=t.id,
        org_id=t.org_id,
        created_by=t.created_by,
        title=t.title,
        description=t.description,
        starts_at=t.starts_at,
        ends_at=t.ends_at,
        location=t.location,
        capacity=t.capacity,
        status=t.status.value,
    )

@router.patch("/{trail_id}", response_model=TrailRead)
async def update_trail(
    trail_id: uuid.UUID,
    payload: TrailUpdate,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    t = await _require_trail_for_organiser(db, trail_id, claims)

    if payload.title is not None:
        t.title = payload.title
    if payload.description is not None:
        t.description = payload.description
    if payload.starts_at is not None:
        t.starts_at = payload.starts_at
    if payload.ends_at is not None:
        t.ends_at = payload.ends_at
    if payload.location is not None:
        t.location = payload.location
    if payload.capacity is not None:
        if payload.capacity <= 0:
            raise HTTPException(status_code=400, detail="Capacity must be > 0")
        t.capacity = payload.capacity
    if payload.status is not None:
        try:
            t.status = TrailStatus(payload.status)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid status")

    await db.commit()
    await db.refresh(t)
    return TrailRead(
        id=t.id,
        org_id=t.org_id,
        created_by=t.created_by,
        title=t.title,
        description=t.description,
        starts_at=t.starts_at,
        ends_at=t.ends_at,
        location=t.location,
        capacity=t.capacity,
        status=t.status.value,
    )


@router.get("/{trail_id}/activities", response_model=list[TrailActivityRead])
async def list_trail_activities(
    trail_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    await _require_trail_for_organiser(db, trail_id, claims)
    rows = (
        await db.execute(
            select(TrailActivity)
            .where(TrailActivity.trail_id == trail_id)
            .order_by(TrailActivity.order.asc())
        )
    ).scalars().all()
    return [_activity_to_schema(row) for row in rows]


@router.post("/{trail_id}/activities", response_model=TrailActivityRead, status_code=201)
async def create_trail_activity(
    trail_id: uuid.UUID,
    payload: TrailActivityCreate,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    await _require_trail_for_organiser(db, trail_id, claims)

    count = (
        await db.execute(
            select(func.count()).where(TrailActivity.trail_id == trail_id)
        )
    ).scalar_one()

    desired_order = payload.order if payload.order is not None else count + 1
    desired_order = max(1, int(desired_order))
    if desired_order > count + 1:
        desired_order = count + 1

    if desired_order <= count:
        await db.execute(
            update(TrailActivity)
            .where(
                TrailActivity.trail_id == trail_id,
                TrailActivity.order >= desired_order,
            )
            .values(order=TrailActivity.order + 1)
        )

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be blank")

    notes = None
    if payload.notes is not None:
        stripped = payload.notes.strip()
        notes = stripped if stripped else None

    entity = TrailActivity(
        trail_id=trail_id,
        order=desired_order,
        title=title,
        points=payload.points if payload.points is not None else 0,
        notes=notes,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return _activity_to_schema(entity)


@router.patch("/{trail_id}/activities/{activity_id}", response_model=TrailActivityRead)
async def update_trail_activity(
    trail_id: uuid.UUID,
    activity_id: uuid.UUID,
    payload: TrailActivityUpdate,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    await _require_trail_for_organiser(db, trail_id, claims)

    activity = (
        await db.execute(
            select(TrailActivity).where(
                TrailActivity.id == activity_id,
                TrailActivity.trail_id == trail_id,
            )
        )
    ).scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if payload.order is not None:
        total = (
            await db.execute(
                select(func.count()).where(TrailActivity.trail_id == trail_id)
            )
        ).scalar_one()
        desired_order = max(1, int(payload.order))
        if desired_order > total:
            desired_order = total
        if desired_order != activity.order:
            if desired_order < activity.order:
                await db.execute(
                    update(TrailActivity)
                    .where(
                        TrailActivity.trail_id == trail_id,
                        TrailActivity.order >= desired_order,
                        TrailActivity.order < activity.order,
                        TrailActivity.id != activity.id,
                    )
                    .values(order=TrailActivity.order + 1)
                )
            else:
                await db.execute(
                    update(TrailActivity)
                    .where(
                        TrailActivity.trail_id == trail_id,
                        TrailActivity.order <= desired_order,
                        TrailActivity.order > activity.order,
                        TrailActivity.id != activity.id,
                    )
                    .values(order=TrailActivity.order - 1)
                )
            activity.order = desired_order

    if payload.title is not None:
        stripped_title = payload.title.strip()
        if not stripped_title:
            raise HTTPException(status_code=400, detail="Title cannot be blank")
        activity.title = stripped_title
    if payload.points is not None:
        activity.points = payload.points
    if "notes" in payload.model_fields_set:
        if payload.notes is None:
            activity.notes = None
        else:
            stripped = payload.notes.strip()
            activity.notes = stripped if stripped else None

    await db.commit()
    await db.refresh(activity)
    return _activity_to_schema(activity)


@router.delete("/{trail_id}/activities/{activity_id}", status_code=204)
async def delete_trail_activity(
    trail_id: uuid.UUID,
    activity_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    await _require_trail_for_organiser(db, trail_id, claims)

    activity = (
        await db.execute(
            select(TrailActivity).where(
                TrailActivity.id == activity_id,
                TrailActivity.trail_id == trail_id,
            )
        )
    ).scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    removed_order = activity.order
    await db.delete(activity)
    await db.execute(
        update(TrailActivity)
        .where(
            TrailActivity.trail_id == trail_id,
            TrailActivity.order > removed_order,
        )
        .values(order=TrailActivity.order - 1)
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reports/orgs/{org_id}/overview", response_model=TrailsOverview)
async def trails_overview(
    org_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    _ensure_report_scope(claims, org_id)

    status_counts = (
        await db.execute(
            select(Trail.status, func.count())
            .where(Trail.org_id == org_id)
            .group_by(Trail.status)
        )
    ).all()
    status_map = {row[0]: int(row[1]) for row in status_counts}

    total_capacity = (
        await db.execute(
            select(func.coalesce(func.sum(Trail.capacity), 0)).where(Trail.org_id == org_id)
        )
    ).scalar_one()

    confirmed_total = (
        await db.execute(
            select(func.count())
            .select_from(Registration)
            .where(Registration.org_id == org_id, Registration.status == RegStatus.CONFIRMED)
        )
    ).scalar_one()

    now = datetime.now(timezone.utc)
    confirmed_expr = func.count(Registration.id).filter(Registration.status == RegStatus.CONFIRMED)
    trail_columns = (
        Trail.id,
        Trail.title,
        Trail.starts_at,
        Trail.ends_at,
        Trail.capacity,
    )
    upcoming_rows = (
        await db.execute(
            select(*trail_columns, confirmed_expr.label("confirmed"))
            .outerjoin(Registration, Registration.trail_id == Trail.id)
            .where(
                Trail.org_id == org_id,
                Trail.status == TrailStatus.PUBLISHED,
                Trail.starts_at >= now,
            )
            .group_by(*trail_columns)
            .order_by(Trail.starts_at.asc())
            .limit(3)
        )
    ).all()

    upcoming: list[UpcomingTrailSummary] = []
    for trail_id, title, starts_at, ends_at, capacity, confirmed in upcoming_rows:
        upcoming.append(
            UpcomingTrailSummary(
                id=trail_id,
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                capacity=capacity,
                confirmed_registrations=int(confirmed or 0),
            )
        )

    total_trails = sum(status_map.values())
    return TrailsOverview(
        org_id=org_id,
        total_trails=total_trails,
        draft=status_map.get(TrailStatus.DRAFT, 0),
        published=status_map.get(TrailStatus.PUBLISHED, 0),
        closed=status_map.get(TrailStatus.CLOSED, 0),
        cancelled=status_map.get(TrailStatus.CANCELLED, 0),
        total_capacity=int(total_capacity or 0),
        confirmed_registrations=int(confirmed_total or 0),
        upcoming=upcoming,
    )

@router.get("/{trail_id}/registrations/by-user/{user_id}")
async def registration_status_for_user(
    trail_id: uuid.UUID,
    user_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
):
    # 1) Trail must exist
    t = await _fetch_trail(db, trail_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trail not found")

    # 2) Authorize: same user OR organiser in same org
    is_self = (claims.get("sub") == str(user_id))
    is_org = claims.get("role") == "organiser" and str(t.org_id) in [str(x) for x in claims.get("org_ids", [])]
    is_service = (claims.get("role") == "service")
    if not (is_self or is_org or is_service):
        raise HTTPException(status_code=403, detail="Forbidden")

    # 3) Lookup registration
    r = (await db.execute(
        select(Registration).where(
            Registration.trail_id == trail_id,
            Registration.user_id == user_id
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="No registration")

    return {"status": r.status.value}
