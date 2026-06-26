"""Wiki-sync job listing + manual raw fork."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import Ticket, WikiSyncJob
from ..services import wiki

router = APIRouter(tags=["wiki"])


@router.get("/wiki-sync/jobs", response_model=list[schemas.WikiSyncJobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.scalars(select(WikiSyncJob).order_by(WikiSyncJob.id.desc())).all()


@router.post("/wiki-sync/tickets/{ticket_id}/fork-raw", response_model=schemas.ForkRawResult)
def fork_raw(ticket_id: int, body: schemas.ForkRawRequest, db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    path = wiki.fork_raw(db, ticket, body.note_md)
    db.add(WikiSyncJob(ticket_id=ticket.id, raw_path=path))
    db.commit()
    return schemas.ForkRawResult(raw_path=path)
