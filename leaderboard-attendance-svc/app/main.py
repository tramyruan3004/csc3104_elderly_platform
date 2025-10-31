from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

from .db import init_db, async_session_maker
from .core.config import get_settings
from .core.nats import nats_connect, nats_close, subscribe_checkins
from .services.ingest import ingest_checkin_evt
from .services.ranks import rebuild_ranks_for_period
from .routers import attendance, leaderboard

settings = get_settings()
scheduler = AsyncIOScheduler()

def current_ym() -> int:
    now = datetime.utcnow()
    return now.year * 100 + now.month

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # NATS consumer: checkins.recorded -> ingest + increment aggregates
    if settings.enable_nats_consumer:
        try:
            await nats_connect()

            async def handle_checkin(evt: dict):
                import uuid, datetime as dt
                try:
                    trail_id = uuid.UUID(evt["trail_id"])
                    org_id = uuid.UUID(evt["org_id"])
                    user_id = uuid.UUID(evt["user_id"])
                    checked_at_iso = evt.get("checked_at")
                    checked_at = dt.datetime.fromisoformat(checked_at_iso.replace("Z", "+00:00")) if checked_at_iso else None
                except Exception:
                    return
                async with async_session_maker() as db:
                    await ingest_checkin_evt(db, trail_id=trail_id, org_id=org_id, user_id=user_id, checked_at=checked_at)

            await subscribe_checkins(handle_checkin)
        except Exception:
            pass

    # Cron: periodically (every N seconds) rebuild current month's ranks (cheap)
    scheduler.add_job(lambda: None, "interval", seconds=999999)  # placeholder to ensure scheduler init on some envs
    scheduler.add_job(rebuild_current_period_ranks, "interval", seconds=settings.ranks_rebuild_interval_sec)
    scheduler.start()

    yield

    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        await nats_close()
    except Exception:
        pass

async def rebuild_current_period_ranks():
    try:
        async with async_session_maker() as db:
            await rebuild_ranks_for_period(db, current_ym())
    except Exception:
        pass

app = FastAPI(title="leaderboard-attendance-svc", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(attendance.router)
app.include_router(leaderboard.router)

@app.get("/health")
async def health():
    return {"status":"ok","service":"leaderboard-attendance-svc"}

Instrumentator().instrument(app).expose(app)
