from __future__ import annotations
import json
from typing import Sequence, Awaitable, Callable
from nats.aio.client import Client as NATS
from ..core.config import get_settings

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

async def subscribe_checkins(cb: Callable[[dict], Awaitable[None]]):
    """
    Subscribe to checkins.recorded and invoke cb(evt_dict).
    evt example:
      {
        "trail_id": "...",
        "org_id": "...",
        "user_id": "...",
        "checked_at": "2025-10-23T18:00:00Z",
        "idempotency_key": "trail_id:user_id"
      }
    """
    await nats_connect()
    async def _handler(msg):
        try:
            data = json.loads(msg.data)
            await cb(data)
        except Exception:
            # swallow to avoid breaking subscription; add logging if you want
            pass
    await _nats.subscribe(_settings.nats_subject_checkin, cb=_handler)
