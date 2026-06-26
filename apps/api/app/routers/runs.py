"""Agent run retrieval/cancel + queue listing/reorder/cancel."""
from __future__ import annotations

import os
import signal
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, transitions as T
from ..db import SessionLocal, get_db
from ..models import AgentRun, QueueItem
from ..services import lifecycle

router = APIRouter(tags=["runs"])

_TERMINAL_RUN = {"success", "failed", "canceled"}


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


def _cancel_ticket_for_run(db: Session, run: AgentRun) -> None:
    """Keep the ticket lifecycle in sync when its active/queued run is canceled."""
    ticket = run.ticket
    if ticket.status not in T.TERMINAL:
        lifecycle.transition_ticket(
            db,
            ticket,
            T.CANCELED,
            actor="Kay",
            reason_md=f"Agent run #{run.run_number} was canceled.",
        )


@router.get("/runs/{run_id}", response_model=schemas.AgentRunDetailOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return run


@router.get("/runs/{run_id}/log")
def get_run_log(run_id: int, offset: int = 0, db: Session = Depends(get_db)):
    """Polling tail of the run's log from a byte offset (§13 fallback)."""
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    content, new_offset = "", offset
    if run.log_path and os.path.exists(run.log_path):
        with open(run.log_path, "rb") as f:
            data = f.read()
        content = data[offset:].decode("utf-8", "ignore")
        new_offset = len(data)
    return {"offset": new_offset, "content": content, "eof": run.status in _TERMINAL_RUN}


@router.get("/runs/{run_id}/stream")
def stream_run_log(run_id: int):
    """SSE live tail of the run log (§13 primary). Streams new bytes until the run
    terminates (bounded). Real mode pipes the tmux pane into the same log file."""
    def gen():
        last = 0
        for _ in range(600):  # ~60s safety bound
            db = SessionLocal()
            try:
                run = db.get(AgentRun, run_id)
                if run is None:
                    yield "event: error\ndata: run not found\n\n"
                    return
                path, status = run.log_path, run.status
            finally:
                db.close()
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                if len(data) > last:
                    for line in data[last:].decode("utf-8", "ignore").splitlines():
                        yield f"data: {line}\n\n"
                    last = len(data)
            if status in _TERMINAL_RUN:
                yield "event: done\ndata: eof\n\n"
                return
            time.sleep(0.1)
        yield "event: done\ndata: timeout\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel", response_model=schemas.AgentRunOut)
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    if run.status in {"success", "failed", "canceled"}:
        raise HTTPException(409, f"Run already finished ({run.status})")
    _cancel_run(run)
    _cancel_ticket_for_run(db, run)
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
            _cancel_ticket_for_run(db, run)
    db.commit()
    db.refresh(qi)
    return qi
