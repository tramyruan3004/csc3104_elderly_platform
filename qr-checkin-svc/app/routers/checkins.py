from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db, get_claims, trails_get_registration_status, points_award_checkin
from ..core.qr import sign_qr, verify_qr
from ..schemas import QRCreateResponse, CheckinCreate, CheckinRead
from ..models import Checkin
from ..services.checkins import record_checkin
from ..core.redis import used_qr_once, allow_request
from ..core.nats import publish_checkin
from ..core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/checkin", tags=["checkin"])

def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# --- 1) Organiser generates a signed QR token for a trail (short TTL)
@router.post("/trails/{trail_id}/qr", response_model=QRCreateResponse, status_code=201)
async def create_qr_for_trail(trail_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=403, detail="Organiser role required")
    org_ids = [uuid.UUID(x) for x in claims.get("org_ids", [])]
    if not org_ids:
        raise HTTPException(status_code=400, detail="Organiser has no organisations")
    org_id = org_ids[0]
    token, exp = sign_qr(trail_id=trail_id, org_id=org_id, issuer_id=uuid.UUID(claims["sub"]))
    url = f"/checkin/scan?token={token}"
    return QRCreateResponse(token=token, expires_at=exp, url=url)

# (Optional) PNG for kiosk demo
@router.get("/trails/{trail_id}/qr.png")
async def create_qr_png(trail_id: uuid.UUID, claims: dict = Depends(get_claims)):
    import qrcode
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=403, detail="Organiser role required")
    org_ids = claims.get("org_ids", [])
    if not org_ids:
        raise HTTPException(status_code=400, detail="No org")
    token, _ = sign_qr(trail_id=trail_id, org_id=uuid.UUID(org_ids[0]), issuer_id=uuid.UUID(claims["sub"]))
    img = qrcode.make(f"/checkin/scan?token={token}")
    from io import BytesIO
    b = BytesIO(); img.save(b, format="PNG")
    return Response(content=b.getvalue(), media_type="image/png")

# --- 2) Attendee scans QR: POST with token; verify+record check-in with replay-guard and rate-limit
@router.post("/scan", response_model=CheckinRead, status_code=201)
async def scan_and_checkin(
    payload: CheckinCreate,
    request: Request,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    # basic rate-limit per IP on scan
    ip = request.client.host if request.client else "unknown"
    if not await allow_request(ip, "checkin.scan"):
        raise HTTPException(status_code=429, detail="Too many requests")

    # a) verify QR token
    try:
        qr = verify_qr(payload.token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired QR")

    trail_id = uuid.UUID(qr["trail_id"])
    org_id = uuid.UUID(qr["org_id"])
    attendee_id = uuid.UUID(claims["sub"])

    # b) replay guard on QR JTI (Redis)
    jti = qr.get("jti")
    ttl = settings.qr_ttl_seconds
    if not jti or not await used_qr_once(jti, ttl):
        # Already used by someone in TTL window → block
        raise HTTPException(status_code=409, detail="QR already used")

    # c) eligibility: must be confirmed in trails-activities-svc
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token header")
    raw_token = authorization.split(" ", 1)[1].strip()

    status_txt = await trails_get_registration_status(
        token=raw_token, trail_id=str(trail_id), user_id=str(attendee_id)
    )
    if status_txt != "confirmed":
        raise HTTPException(status_code=403, detail="Not confirmed for this trail")

    # d) write check-in (DB idempotency guarantees one per user+trail)
    obj, created = await record_checkin(
        db,
        trail_id=trail_id,
        org_id=org_id,
        user_id=attendee_id,
        checked_by=None,
        method="qr",
    )

    # e) Emit event on NATS (idempotency key helps consumers)
    try:
        await publish_checkin({
            "trail_id": str(trail_id),
            "org_id": str(org_id),
            "user_id": str(attendee_id),
            "checked_at": _now_iso(),
            "idempotency_key": f"{trail_id}:{attendee_id}"
        })
    except Exception:
        # non-fatal for the check-in HTTP response
        pass

    # f) Award points: NATS-only or HTTP fallback
    if not settings.use_nats_for_points:
        try:
            await points_award_checkin(
                token=raw_token,
                trail_id=str(trail_id),
                user_id=str(attendee_id),
                org_id=str(org_id),
                checked_at=_now_iso(),
            )
        except Exception:
            pass

    return CheckinRead(
        id=obj.id, trail_id=obj.trail_id, org_id=obj.org_id, user_id=obj.user_id,
        method=obj.method, checked_at=obj.checked_at, checked_by=obj.checked_by
    )

# --- 3) Organiser roster
@router.get("/trails/{trail_id}/roster", response_model=list[CheckinRead])
async def roster(trail_id: uuid.UUID, claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=403, detail="Organiser role required")
    rows = (await db.execute(select(Checkin).where(Checkin.trail_id == trail_id).order_by(Checkin.checked_at.asc()))).scalars().all()
    return [CheckinRead(id=r.id, trail_id=r.trail_id, org_id=r.org_id, user_id=r.user_id, method=r.method, checked_at=r.checked_at, checked_by=r.checked_by) for r in rows]

# --- 4) Attendee history
@router.get("/users/me", response_model=list[CheckinRead])
async def my_checkins(claims: dict = Depends(get_claims), db: AsyncSession = Depends(get_db)):
    uid = uuid.UUID(claims["sub"])
    rows = (await db.execute(select(Checkin).where(Checkin.user_id == uid).order_by(Checkin.checked_at.desc()))).scalars().all()
    return [CheckinRead(id=r.id, trail_id=r.trail_id, org_id=r.org_id, user_id=r.user_id, method=r.method, checked_at=r.checked_at, checked_by=r.checked_by) for r in rows]
