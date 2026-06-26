"""Central ticket lifecycle: validate + apply a status transition, record the
StatusEvent, write the LLM Wiki raw event, and enqueue a wiki sync job.

All status changes (router transition, watcher auto-move, review) funnel through
`transition_ticket` so every change is recorded identically.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import transitions as T
from ..models import StatusBlock, StatusEvent, Ticket, WikiSyncJob
from . import wiki


class TransitionError(Exception):
    def __init__(self, frm: str, to: str):
        self.frm, self.to = frm, to
        super().__init__(f"Illegal transition: {frm!r} -> {to!r}")


def get_status_block(db: Session, board_id: int, name: str) -> StatusBlock | None:
    return db.scalars(
        select(StatusBlock).where(StatusBlock.board_id == board_id, StatusBlock.name == name)
    ).first()


def transition_ticket(
    db: Session,
    ticket: Ticket,
    to_status: str,
    actor: str = "system",
    reason_md: str | None = None,
    run=None,
    enforce: bool = True,
) -> StatusEvent:
    frm = ticket.status
    if enforce and not T.can_transition(frm, to_status):
        raise TransitionError(frm, to_status)

    block = get_status_block(db, ticket.board_id, to_status)
    if block is None:
        raise ValueError(f"Unknown status block {to_status!r} on board {ticket.board_id}")

    now = datetime.utcnow()
    ticket.status_block_id = block.id
    if to_status == T.IN_PROGRESS and ticket.started_at is None:
        ticket.started_at = now
    if to_status == T.COMPLETED:
        ticket.completed_at = now
    if to_status == T.CANCELED:
        ticket.canceled_at = now

    event = StatusEvent(
        ticket_id=ticket.id, from_status=frm or None, to_status=to_status,
        actor=actor, reason_md=reason_md,
    )
    db.add(event)
    db.flush()  # assign event.id for the filename

    raw_path = wiki.write_status_event(db, ticket, event, run=run)
    event.wiki_raw_path = raw_path
    db.add(WikiSyncJob(ticket_id=ticket.id, raw_path=raw_path, scheduled_at=None))
    db.flush()
    return event
