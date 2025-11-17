from __future__ import annotations
import asyncio
import redis.asyncio as redis
from .config import get_settings

_settings = get_settings()
_r: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _r
    if _r is None:
        _r = redis.from_url(_settings.redis_url, decode_responses=True)
    return _r

async def ping_redis() -> bool:
    try:
        r = get_redis()
        pong = await r.ping()
        return bool(pong)
    except Exception:
        return False

# ---- Replay guard for QR JTI ----
async def reserve_qr_token(jti: str, ttl_seconds: int) -> bool:
    """
    Try to reserve a QR token. Returns True if this caller now owns the token,
    or False if another scan already completed with the same JTI.
    """
    r = get_redis()
    ok = await r.set(f"qr:jti:{jti}", "pending", ex=ttl_seconds, nx=True)
    return bool(ok)


async def release_qr_token(jti: str) -> None:
    """
    Release a reserved token so the attendee can retry (used when the scan fails
    before the check-in is committed).
    """
    r = get_redis()
    try:
        await r.delete(f"qr:jti:{jti}")
    except Exception:
        pass

async def allow_request(ip: str, route_key: str) -> bool:
    """
    Fixed window: increment a counter key; allow if <= max.
    """
    if not _settings.rl_enabled:
        return True
    r = get_redis()
    key = f"rl:{route_key}:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _settings.rl_window_seconds)
    count, _ = await pipe.execute()
    return int(count) <= _settings.rl_max_reqs
