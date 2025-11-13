from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response, Header, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from urllib.parse import urlencode

from ..deps import (
    get_db,
    get_claims,
    trails_get_registration_status,
    points_award_checkin,
    trails_get_trail_details,
)
from ..core.qr import sign_qr, verify_qr
from ..schemas import QRCreateResponse, CheckinCreate, CheckinRead, QRActivityCreate
from ..models import Checkin
from ..services.checkins import record_checkin, record_activity_checkin
from ..core.redis import reserve_qr_token, release_qr_token, allow_request
from ..core.nats import publish_checkin
from ..core.config import get_settings
from ..observability import record_qr_token_issued, record_checkin_scan

settings = get_settings()
router = APIRouter(prefix="/checkin", tags=["checkin"])

def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


async def _determine_qr_ttl_seconds(
    *,
    trail_id: uuid.UUID,
    org_id: uuid.UUID,
    authorization: str | None,
) -> int:
    base_ttl = settings.qr_ttl_seconds
    details = await trails_get_trail_details(
        trail_id=str(trail_id),
        org_id=str(org_id),
        authorization_header=authorization,
    )
    if not details:
        return base_ttl

    ends_at = _parse_iso_datetime(details.get("ends_at"))
    if not ends_at:
        return base_ttl

    now = datetime.now(timezone.utc)
    remaining = int((ends_at - now).total_seconds())
    if remaining <= 0:
        return base_ttl

    grace = settings.qr_trail_grace_seconds if settings.qr_trail_grace_seconds > 0 else 0
    desired = remaining + grace
    if settings.qr_max_ttl_seconds > 0:
        desired = min(desired, settings.qr_max_ttl_seconds)

    return max(base_ttl, desired)

# --- 1) Organiser generates a signed QR token for a trail (short TTL)
@router.post("/trails/{trail_id}/qr", response_model=QRCreateResponse, status_code=201)
async def create_qr_for_trail(
    trail_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=403, detail="Organiser role required")
    org_ids = [uuid.UUID(x) for x in claims.get("org_ids", [])]
    if not org_ids:
        raise HTTPException(status_code=400, detail="Organiser has no organisations")
    org_id = org_ids[0]
    ttl_seconds = await _determine_qr_ttl_seconds(
        trail_id=trail_id,
        org_id=org_id,
        authorization=authorization,
    )
    token, exp = sign_qr(
        trail_id=trail_id,
        org_id=org_id,
        issuer_id=uuid.UUID(claims["sub"]),
        ttl_seconds=ttl_seconds,
    )
    url = f"/checkin/scan?{urlencode({'token': token})}"
    record_qr_token_issued(org_id=org_id, trail_id=trail_id, kind="trail", expires_at=exp)
    return QRCreateResponse(token=token, expires_at=exp, url=url)


@router.post(
    "/trails/{trail_id}/activities/{activity_id}/qr",
    response_model=QRCreateResponse,
    status_code=201,
)
async def create_qr_for_activity(
    trail_id: uuid.UUID,
    activity_id: uuid.UUID,
    payload: QRActivityCreate | None = Body(default=None),
    claims: dict = Depends(get_claims),
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=403, detail="Organiser role required")
    org_ids = [uuid.UUID(x) for x in claims.get("org_ids", [])]
    if not org_ids:
        raise HTTPException(status_code=400, detail="Organiser has no organisations")
    org_id = org_ids[0]

    activity_order = payload.activity_order if payload else None
    points = payload.points if payload else None

    ttl_seconds = await _determine_qr_ttl_seconds(
        trail_id=trail_id,
        org_id=org_id,
        authorization=authorization,
    )

    token, exp = sign_qr(
        trail_id=trail_id,
        org_id=org_id,
        issuer_id=uuid.UUID(claims["sub"]),
        activity_id=activity_id,
        activity_order=activity_order,
        points=points,
        ttl_seconds=ttl_seconds,
    )
    query: dict[str, str] = {"token": token, "t": str(activity_id)}
    if activity_order is not None:
        query["a"] = str(activity_order)
    if points is not None:
        query["p"] = str(points)
    url = f"/checkin/scan?{urlencode(query)}"
    record_qr_token_issued(
        org_id=org_id,
        trail_id=trail_id,
        kind="activity",
        expires_at=exp,
        activity_id=activity_id,
    )
    return QRCreateResponse(
        token=token,
        expires_at=exp,
        url=url,
        activity_id=activity_id,
        activity_order=activity_order,
        points=points,
    )

# (Optional) PNG for kiosk demo
@router.get("/trails/{trail_id}/qr.png")
async def create_qr_png(
    trail_id: uuid.UUID,
    claims: dict = Depends(get_claims),
    authorization: str | None = Header(default=None),
):
    try:
        import qrcode  # type: ignore[import]
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="QR generator not available") from exc
    if claims.get("role") != "organiser":
        raise HTTPException(status_code=403, detail="Organiser role required")
    org_ids = claims.get("org_ids", [])
    if not org_ids:
        raise HTTPException(status_code=400, detail="No org")
    org_uuid = uuid.UUID(org_ids[0])
    ttl_seconds = await _determine_qr_ttl_seconds(
        trail_id=trail_id,
        org_id=org_uuid,
        authorization=authorization,
    )
    token, _ = sign_qr(
        trail_id=trail_id,
        org_id=org_uuid,
        issuer_id=uuid.UUID(claims["sub"]),
        ttl_seconds=ttl_seconds,
    )
    img = qrcode.make(f"/checkin/scan?token={token}")
    from io import BytesIO
    b = BytesIO()
    try:
        img.save(b, format="PNG")
    except TypeError:
        # Handle backends like PyPNG that do not accept the format argument
        try:
            pil_img = img.get_image()
            pil_img.save(b, format="PNG")
        except Exception:
            img.save(b)
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
    user_id = uuid.UUID(claims["sub"])
    org_uuid: uuid.UUID | None = None
    trail_uuid: uuid.UUID | None = None
    activity_uuid: uuid.UUID | None = None
    outcome_logged = False

    def log_outcome(result: str, *, reason: str | None = None) -> None:
        nonlocal outcome_logged
        record_checkin_scan(
            org_id=org_uuid,
            trail_id=trail_uuid,
            user_id=user_id,
            activity_id=activity_uuid,
            result=result,
            reason=reason,
        )
        outcome_logged = True

    # basic rate-limit per IP on scan
    ip = request.client.host if request.client else "unknown"
    if not await allow_request(ip, "checkin.scan"):
        log_outcome("rate_limited", reason="ip_limit")
        raise HTTPException(status_code=429, detail="Too many requests")

    # a) verify QR token
    try:
        qr = verify_qr(payload.token)
    except Exception:
        log_outcome("invalid_qr", reason="token_invalid")
        raise HTTPException(status_code=400, detail="Invalid or expired QR")

    trail_id = uuid.UUID(qr["trail_id"])
    org_id = uuid.UUID(qr["org_id"])
    attendee_id = user_id
    trail_uuid = trail_id
    org_uuid = org_id

    token_activity_uuid_raw = qr.get("activity_id")
    token_activity_uuid: uuid.UUID | None = None
    if token_activity_uuid_raw is not None:
        try:
            token_activity_uuid = uuid.UUID(str(token_activity_uuid_raw))
        except Exception:
            raise HTTPException(status_code=400, detail="QR activity metadata is invalid")

    activity_uuid = token_activity_uuid or payload.activity_id

    if (
        token_activity_uuid is not None
        and payload.activity_id is not None
        and payload.activity_id != token_activity_uuid
    ):
        # Always prefer the activity embedded in the QR token when present.
        activity_uuid = token_activity_uuid

    def _coerce_int(value):
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            raise HTTPException(status_code=400, detail="QR activity metadata is invalid")

    token_activity_order = _coerce_int(qr.get("activity_order"))
    activity_order = (
        token_activity_order
        if token_activity_order is not None
        else payload.activity_order
    )

    token_points_override = _coerce_int(qr.get("points"))
    points_override = (
        token_points_override
        if token_points_override is not None
        else payload.points
    )
    if (activity_order is not None or points_override is not None) and activity_uuid is None:
        raise HTTPException(status_code=400, detail="activity_id is required when providing activity metadata")

    claim_orgs = {str(x) for x in claims.get("org_ids", []) if x}
    if not claim_orgs:
        log_outcome("forbidden", reason="no_org_membership")
        raise HTTPException(status_code=403, detail="Join an organisation before scanning activities")
    if str(org_id) not in claim_orgs:
        log_outcome("forbidden", reason="org_mismatch")
        raise HTTPException(status_code=403, detail="You are not a member of this organisation")

    # b) replay guard on QR JTI (Redis)
    jti = qr.get("jti")
    ttl = settings.qr_ttl_seconds
    exp_claim = qr.get("exp")
    if isinstance(exp_claim, (int, float)):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        ttl = max(1, int(exp_claim) - now_ts)
    if not jti:
        raise HTTPException(status_code=400, detail="QR token missing identifier")
    if not await reserve_qr_token(jti, ttl):
        log_outcome("replay", reason="token_reuse")
        raise HTTPException(status_code=409, detail="QR already used")
    checkin_created = False
    activity_created = False
    activity_obj = None

    # c) eligibility: must be confirmed in trails-activities-svc
    if not authorization or not authorization.lower().startswith("bearer "):
        await release_qr_token(jti)
        log_outcome("missing_authorization", reason="token_header_required")
        raise HTTPException(status_code=401, detail="Missing token header")
    raw_token = authorization.split(" ", 1)[1].strip()

    try:
        status_txt = await trails_get_registration_status(
            token=raw_token, trail_id=str(trail_id), user_id=str(attendee_id)
        )
        if status_txt != "confirmed":
            log_outcome("not_confirmed", reason=status_txt or "unconfirmed")
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
        checkin_created = created

        if activity_uuid:
            points_value = int(points_override) if points_override is not None else 0
            activity_obj, activity_created = await record_activity_checkin(
                db,
                trail_id=trail_id,
                activity_id=activity_uuid,
                user_id=attendee_id,
                activity_order=activity_order,
                points_awarded=points_value,
            )
            activity_order = activity_obj.activity_order
    except HTTPException as exc:
        if not checkin_created and not activity_created:
            await release_qr_token(jti)
        if not outcome_logged:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            log_outcome("http_error", reason=detail)
        raise
    except Exception as exc:
        if not checkin_created and not activity_created:
            await release_qr_token(jti)
        if not outcome_logged:
            log_outcome("error", reason=str(exc))
        raise

    # e) Emit event on NATS (idempotency key helps consumers)
    points_awarded = int(activity_obj.points_awarded) if activity_obj else None
    event_payload = {
        "trail_id": str(trail_id),
        "org_id": str(org_id),
        "user_id": str(attendee_id),
        "checked_at": _now_iso(),
        "idempotency_key": f"{trail_id}:{attendee_id}:{activity_uuid}" if activity_uuid else f"{trail_id}:{attendee_id}",
        "new_attendance": checkin_created,
    }
    if activity_uuid:
        event_payload["activity_id"] = str(activity_uuid)
        event_payload["activity_order"] = activity_order
        event_payload["new_activity"] = activity_created
        event_payload["points_awarded"] = points_awarded
    try:
        await publish_checkin(event_payload)
    except Exception:
        # non-fatal for the check-in HTTP response
        pass

    # f) Award points: NATS-only or HTTP fallback
    should_award_via_http = False
    points_delta = None
    if checkin_created:
        should_award_via_http = True
    if activity_uuid and activity_created and points_awarded is not None and points_awarded > 0:
        should_award_via_http = True
        points_delta = points_awarded

    if not settings.use_nats_for_points and should_award_via_http:
        try:
            await points_award_checkin(
                token=raw_token,
                trail_id=str(trail_id),
                user_id=str(attendee_id),
                org_id=str(org_id),
                checked_at=_now_iso(),
                activity_id=str(activity_uuid) if activity_uuid else None,
                activity_order=activity_order,
                points_delta=points_delta,
                new_attendance=checkin_created,
            )
        except Exception:
            pass

    if not outcome_logged:
        outcome_reason = "new_attendance" if checkin_created else "repeat"
        if activity_uuid and activity_created:
            outcome_reason = "activity"
        log_outcome("success", reason=outcome_reason)

    return CheckinRead(
        id=obj.id,
        trail_id=obj.trail_id,
        org_id=obj.org_id,
        user_id=obj.user_id,
        method=obj.method,
        checked_at=obj.checked_at,
        checked_by=obj.checked_by,
        activity_id=activity_uuid,
        activity_order=activity_order,
        points_awarded=points_awarded,
        new_attendance=checkin_created,
        new_activity=activity_created,
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
