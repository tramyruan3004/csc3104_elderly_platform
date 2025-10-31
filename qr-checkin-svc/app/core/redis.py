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
async def used_qr_once(jti: str, ttl_seconds: int) -> bool:
    """
    Return True if we successfully mark this JTI as used (first time),
    return False if it's already present (replay).
    """
    r = get_redis()
    # SET if Not eXists with EXpire
    # NX ensures first caller wins, others see False
    ok = await r.set(f"qr:jti:{jti}", "1", ex=ttl_seconds, nx=True)
    return bool(ok)

# ---- Simple fixed-window rate limit per IP/route ----
async def allow_request(ip: str, route_key: str) -> bool:
    """
    Fixed window: increment a counter key; allow if <= max.
    """
    if not _settings.rl_enabled:
        return True
    r = get_redis()
    key = f"rl:{route_key}:{ip}"
    # INCR, set expire on first increment in a window
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _settings.rl_window_seconds)
    count, _ = await pipe.execute()
    return int(count) <= _settings.rl_max_reqs
