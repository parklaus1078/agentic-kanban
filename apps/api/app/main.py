"""Agent System v2 — FastAPI application entrypoint (app.main:app)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .routers import admin, boards, catalog, runs, tickets, wiki


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
    yield


app = FastAPI(title="Agent System v2", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (admin.router, boards.router, catalog.router, tickets.router, runs.router, wiki.router):
    app.include_router(r)


@app.get("/")
def root():
    return {"name": "Agent System v2", "docs": "/docs", "health": "/health"}
