from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .routers import points, vouchers, rules
from .db import init_db, async_session_maker
from .core.config import get_settings
from .core.nats import nats_connect, nats_close, subscribe_checkins
from .services.points import award_checkin_points

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Start NATS consumer (optional toggle)
    if settings.enable_nats_consumer:
        try:
            await nats_connect()

            async def handle_checkin(evt: dict):
                import uuid
                # expected keys: trail_id, org_id, user_id
                try:
                    trail_id = uuid.UUID(evt["trail_id"])
                    org_id = uuid.UUID(evt["org_id"])
                    user_id = uuid.UUID(evt["user_id"])
                except Exception:
                    return 

                activity_id = None
                activity_order = None
                points_override = None
                new_attendance = evt.get("new_attendance") is True
                new_activity = evt.get("new_activity") is True

                raw_activity_id = evt.get("activity_id")
                if raw_activity_id:
                    try:
                        activity_id = uuid.UUID(raw_activity_id)
                    except Exception:
                        activity_id = None

                raw_order = evt.get("activity_order")
                if raw_order is not None:
                    try:
                        activity_order = int(raw_order)
                    except Exception:
                        activity_order = None

                raw_points = evt.get("points_awarded")
                if raw_points is not None:
                    try:
                        points_override = int(raw_points)
                    except Exception:
                        points_override = None

                has_activity_points = points_override is not None and points_override > 0
                should_award = new_attendance or (new_activity and has_activity_points)
                if not should_award:
                    return

                async with async_session_maker() as db:
                    await award_checkin_points(
                        db,
                        user_id=user_id,
                        org_id=org_id,
                        trail_id=trail_id,
                        details="qr-checkin-nats",
                        points_override=points_override,
                        activity_id=activity_id,
                        activity_order=activity_order,
                    )

            await subscribe_checkins(handle_checkin)
        except Exception:
            pass

    yield

    try:
        await nats_close()
    except Exception:
        pass

app = FastAPI(title="points-vouchers-rules-svc", lifespan=lifespan)

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

app.include_router(points.router)
app.include_router(vouchers.router)
app.include_router(rules.router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "points-vouchers-rules-svc"}

Instrumentator().instrument(app).expose(app)
