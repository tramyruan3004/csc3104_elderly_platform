from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .db import init_db
from .routers import checkins
from .core.redis import ping_redis
from .core.nats import nats_connect, nats_close

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # best-effort connect to infra; service still runs if these fail
    try:
        await nats_connect()
    except Exception:
        pass
    try:
        await ping_redis()
    except Exception:
        pass
    yield
    try:
        await nats_close()
    except Exception:
        pass

app = FastAPI(title="qr-checkin-svc", lifespan=lifespan)

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

app.include_router(checkins.router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "qr-checkin-svc"}

Instrumentator().instrument(app).expose(app)
