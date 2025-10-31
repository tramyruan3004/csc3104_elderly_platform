from __future__ import annotations
from typing import Sequence, Callable, Awaitable
import json
from nats.aio.client import Client as NATS
from .config import get_settings

settings = get_settings()
_nats = NATS()

async def nats_connect():
    if not _nats.is_connected:
        servers: Sequence[str] = [u.strip() for u in settings.nats_urls.split(",") if u.strip()]
        await _nats.connect(servers=servers)

async def nats_close():
    try:
        if _nats.is_connected:
            await _nats.drain()
    except Exception:
        pass

async def subscribe_checkins(cb: Callable[[dict], Awaitable[None]]):
    await nats_connect()
    async def handler(msg):
        try:
            data = json.loads(msg.data)
            await cb(data)
        except Exception:
            # swallow, or add logging
            pass
    await _nats.subscribe(settings.subject_checkin, cb=handler)
