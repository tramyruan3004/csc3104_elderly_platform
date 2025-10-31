from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .db import init_db
from .routers import trails, registrations, users, invites  

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="trails-activities-svc", lifespan=lifespan)

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

app.include_router(trails.router)
app.include_router(registrations.router)
app.include_router(users.router)
app.include_router(invites.router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "trails-activities-svc"}

Instrumentator().instrument(app).expose(app)
