"""Agent run retrieval/cancel + queue listing/reorder/cancel."""
from __future__ import annotations

import os
import signal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import AgentRun, QueueItem

router = APIRouter(tags=["runs"])


def _cancel_run(run: AgentRun) -> None:
    """Mark a run canceled; for a real running process, try to kill it (distinct from
    canceling a still-queued item)."""
    if run.status == "running" and run.process_id and not run.process_id.startswith("sim-"):
        try:
            os.kill(int(run.process_id), signal.SIGTERM)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
    run.status = "canceled"
    run.finished_at = datetime.utcnow()
    run.error = run.error or "canceled"


@router.get("/runs/{run_id}", response_model=schemas.AgentRunDetailOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return run


@router.post("/runs/{run_id}/cancel", response_model=schemas.AgentRunOut)
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    if run.status in {"success", "failed", "canceled"}:
        raise HTTPException(409, f"Run already finished ({run.status})")
    _cancel_run(run)
    qi = db.scalars(select(QueueItem).where(QueueItem.run_id == run.id)).first()
    if qi:
        qi.cancel_requested = True
        qi.state = "canceled"
    db.commit()
    db.refresh(run)
    return run


@router.get("/queue", response_model=list[schemas.QueueItemOut])
def list_queue(db: Session = Depends(get_db)):
    return db.scalars(select(QueueItem).order_by(QueueItem.order_index, QueueItem.id)).all()


@router.patch("/queue/reorder", response_model=list[schemas.QueueItemOut])
def reorder_queue(body: schemas.QueueReorderRequest, db: Session = Depends(get_db)):
    items = {qi.id: qi for qi in db.scalars(select(QueueItem)).all()}
    for position, qid in enumerate(body.ordered_ids):
        if qid in items:
            items[qid].order_index = position
    db.commit()
    return db.scalars(select(QueueItem).order_by(QueueItem.order_index, QueueItem.id)).all()


@router.post("/queue/{queue_item_id}/cancel", response_model=schemas.QueueItemOut)
def cancel_queue_item(queue_item_id: int, db: Session = Depends(get_db)):
    qi = db.get(QueueItem, queue_item_id)
    if qi is None:
        raise HTTPException(404, f"Queue item {queue_item_id} not found")
    if qi.state in {"done", "canceled"}:
        raise HTTPException(409, f"Queue item already {qi.state}")
    qi.cancel_requested = True
    qi.state = "canceled"
    if qi.run_id:
        run = db.get(AgentRun, qi.run_id)
        if run and run.status in {"queued", "running"}:
            _cancel_run(run)
    db.commit()
    db.refresh(qi)
    return qi
