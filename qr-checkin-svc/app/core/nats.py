from __future__ import annotations
import json
from typing import Sequence
from nats.aio.client import Client as NATS
from .config import get_settings

_settings = get_settings()
_nats = NATS()

async def nats_connect():
    if not _nats.is_connected:
        servers: Sequence[str] = [u.strip() for u in _settings.nats_urls.split(",") if u.strip()]
        await _nats.connect(servers=servers)

async def nats_close():
    try:
        if _nats.is_connected:
            await _nats.drain()
    except Exception:
        pass

async def publish_checkin(evt: dict):
    """
    evt = {
      "trail_id": str,
      "org_id": str,
      "user_id": str,
      "checked_at": iso8601,
      "idempotency_key": "trail_id:user_id"
    }
    """
    await nats_connect()
    await _nats.publish(_settings.nats_subject_checkin, json.dumps(evt).encode("utf-8"))
