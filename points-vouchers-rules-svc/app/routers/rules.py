from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_claims
from ..models import Rule, RuleType
from ..schemas import RuleCreate, RuleUpdate, RuleRead

router = APIRouter(prefix="/orgs/{org_id}/rules", tags=["rules"])

def _allow_actor_for_org(claims, org_id: uuid.UUID) -> bool:
    role = claims.get("role")
    org_ids = [str(x) for x in claims.get("org_ids", [])]
    in_scope = (not org_ids) or (str(org_id) in org_ids)  # empty -> global
    return (role == "organiser" and str(org_id) in org_ids) or (role == "service" and in_scope)

@router.get("", response_model=list[RuleRead])
async def list_rules(org_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    rows = (await db.execute(select(Rule).where(Rule.org_id == org_id))).scalars().all()
    return [RuleRead(id=r.id, org_id=r.org_id, type=r.type.value, points=r.points, name=r.name, description=r.description, active=r.active) for r in rows]

@router.post("", response_model=RuleRead, status_code=201)
async def create_rule(org_id: uuid.UUID, payload: RuleCreate, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    try:
        rtype = RuleType(payload.type)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid rule type")
    r = Rule(org_id=org_id, type=rtype, points=payload.points, name=payload.name, description=payload.description, active=payload.active)
    db.add(r); await db.commit(); await db.refresh(r)
    return RuleRead(id=r.id, org_id=r.org_id, type=r.type.value, points=r.points, name=r.name, description=r.description, active=r.active)

@router.patch("/{rule_id}", response_model=RuleRead)
async def update_rule(org_id: uuid.UUID, rule_id: uuid.UUID, payload: RuleUpdate, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if not _allow_actor_for_org(claims, org_id):
        raise HTTPException(status_code=403, detail="Organiser/Service role with org scope required")
    r = (await db.execute(select(Rule).where(Rule.id == rule_id, Rule.org_id == org_id))).scalar_one_or_none()
    if not r: raise HTTPException(status_code=404, detail="Rule not found")
    if payload.points is not None: r.points = payload.points
    if payload.name is not None: r.name = payload.name
    if payload.description is not None: r.description = payload.description
    if payload.active is not None: r.active = payload.active
    await db.commit(); await db.refresh(r)
    return RuleRead(id=r.id, org_id=r.org_id, type=r.type.value, points=r.points, name=r.name, description=r.description, active=r.active)
