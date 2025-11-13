from __future__ import annotations

import json
import logging
from typing import Any

from prometheus_client import Counter, REGISTRY

audit_logger = logging.getLogger("qr_checkin.audit")


def _as_str(value: Any | None) -> str | None:
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return repr(value)


def _log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    audit_logger.info(json.dumps(payload, default=str))


def _counter(name: str, documentation: str, labelnames: tuple[str, ...]) -> Counter:
    existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)  # type: ignore[attr-defined]
    if isinstance(existing, Counter):
        return existing
    return Counter(name, documentation, labelnames=labelnames)


qr_tokens_counter = _counter(
    "qr_tokens_issued_total",
    "QR tokens issued grouped by kind/org.",
    ("org_id", "kind"),
)

checkin_scans_counter = _counter(
    "qr_checkin_events_total",
    "QR check-in attempts grouped by outcome.",
    ("org_id", "result"),
)


def record_qr_token_issued(
    *,
    org_id: Any,
    trail_id: Any,
    kind: str,
    expires_at: Any | None = None,
    activity_id: Any | None = None,
) -> None:
    org_label = _as_str(org_id) or "unknown"
    qr_tokens_counter.labels(org_id=org_label, kind=kind).inc()
    _log_event(
        "qr_token_issued",
        org_id=org_label,
        trail_id=_as_str(trail_id),
        kind=kind,
        activity_id=_as_str(activity_id),
        expires_at=_as_str(expires_at),
    )


def record_checkin_scan(
    *,
    org_id: Any | None,
    trail_id: Any | None,
    user_id: Any | None,
    activity_id: Any | None,
    result: str,
    reason: str | None = None,
) -> None:
    org_label = _as_str(org_id) or "unknown"
    checkin_scans_counter.labels(org_id=org_label, result=result).inc()
    _log_event(
        "qr_checkin_event",
        org_id=org_label,
        trail_id=_as_str(trail_id),
        user_id=_as_str(user_id),
        activity_id=_as_str(activity_id),
        result=result,
        reason=reason,
    )
