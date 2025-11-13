from __future__ import annotations

import json
import logging
from typing import Any

from prometheus_client import Counter, REGISTRY

audit_logger = logging.getLogger("points_vouchers.audit")


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


voucher_redemptions_counter = _counter(
    "voucher_redemptions_total",
    "Voucher redemption attempts partitioned by outcome.",
    ("org_id", "result"),
)

manual_adjustments_counter = _counter(
    "manual_point_adjustments_total",
    "Manual point adjustments partitioned by direction/outcome.",
    ("org_id", "direction", "result"),
)

checkin_awards_counter = _counter(
    "checkin_awards_total",
    "Check-in point awards partitioned by source/outcome.",
    ("org_id", "source", "result"),
)


def record_voucher_redemption(
    *,
    org_id: Any | None,
    voucher_id: Any | None,
    user_id: Any | None,
    points_cost: int | None,
    result: str,
    reason: str | None = None,
) -> None:
    org_label = _as_str(org_id) or "unknown"
    voucher_redemptions_counter.labels(org_id=org_label, result=result).inc()
    _log_event(
        "voucher_redemption",
        org_id=org_label,
        voucher_id=_as_str(voucher_id),
        user_id=_as_str(user_id),
        points_cost=points_cost,
        result=result,
        reason=reason,
    )


def record_manual_adjustment(
    *,
    org_id: Any,
    user_id: Any,
    delta: int,
    reason: str,
    result: str,
    balance: int | None = None,
) -> None:
    direction = "credit" if delta >= 0 else "debit"
    org_label = _as_str(org_id) or "unknown"
    manual_adjustments_counter.labels(org_id=org_label, direction=direction, result=result).inc()
    _log_event(
        "manual_points_adjustment",
        org_id=org_label,
        user_id=_as_str(user_id),
        delta=delta,
        direction=direction,
        reason=reason,
        result=result,
        balance=balance,
    )


def record_checkin_award(
    *,
    org_id: Any,
    user_id: Any,
    trail_id: Any,
    points: int,
    source: str,
    result: str,
    activity_id: Any | None = None,
) -> None:
    org_label = _as_str(org_id) or "unknown"
    checkin_awards_counter.labels(org_id=org_label, source=source, result=result).inc()
    _log_event(
        "checkin_award",
        org_id=org_label,
        user_id=_as_str(user_id),
        trail_id=_as_str(trail_id),
        points=points,
        source=source,
        result=result,
        activity_id=_as_str(activity_id),
    )
