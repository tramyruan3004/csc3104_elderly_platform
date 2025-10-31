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
                    return  # malformed payload

                # IMPORTANT: idempotency is recommended at your award layer.
                # If award_checkin_points is already idempotent (e.g., checks ledger),
                # this is safe. Otherwise consider adding a guard there.
                async with async_session_maker() as db:
                    await award_checkin_points(
                        db,
                        user_id=user_id,
                        org_id=org_id,
                        trail_id=trail_id,
                        details="qr-checkin-nats"
                    )

            await subscribe_checkins(handle_checkin)
        except Exception:
            # You can log the error; service still runs without NATS
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
