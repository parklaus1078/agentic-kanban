"""Health, seed, and manual worker/watcher ticks (so the UI/demo can drive the loop)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas, seed
from ..db import get_db
from ..services import adapter, watcher

router = APIRouter(tags=["admin"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/admin/seed", response_model=schemas.SeedResult)
def run_seed(db: Session = Depends(get_db)):
    board, n_personas, n_skills = seed.seed_all(db)
    return schemas.SeedResult(
        board=schemas.BoardOut.model_validate(board), personas=n_personas, skills=n_skills
    )


@router.post("/admin/worker/tick", response_model=schemas.TickResult)
def worker_tick(db: Session = Depends(get_db)):
    return schemas.TickResult(processed=adapter.worker_tick(db))


@router.post("/admin/watcher/tick", response_model=schemas.WatchTickResult)
def watcher_tick(db: Session = Depends(get_db)):
    return schemas.WatchTickResult(detected=watcher.watcher_tick(db))
