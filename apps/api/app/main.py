"""Agent System v2 — FastAPI application entrypoint (app.main:app)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .routers import admin, boards, catalog, projects, runs, system, tickets, wiki


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.autoseed:
        from . import seed
        db = SessionLocal()
        try:
            seed.seed_all(db)
        finally:
            db.close()
    # Boot recovery (Phase 3): re-queue runs interrupted by a power cut / WSL drop.
    from .services import durability
    db = SessionLocal()
    try:
        n = durability.recover_interrupted_runs(db)
        if n:
            print(f"[recovery] re-queued {n} interrupted run(s)", flush=True)
    finally:
        db.close()
    yield


app = FastAPI(title="Agent System v2", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (admin.router, boards.router, catalog.router, projects.router, tickets.router, runs.router, system.router, wiki.router):
    app.include_router(r)


@app.get("/")
def root():
    return {"name": "Agent System v2", "docs": "/docs", "health": "/health"}
