"""Agent run creation + queueing."""
from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import output_dir_for_agent
from ..models import AgentRun, QueueItem, Ticket
from . import prompt_builder


def next_run_number(db: Session, ticket: Ticket) -> int:
    n = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.ticket_id == ticket.id)) or 0
    return n + 1


def compute_output_path(ticket: Ticket, agent: str, run_number: int) -> str:
    base = output_dir_for_agent(agent)
    return os.path.join(base, ticket.ticket_number.lower(), f"run-{run_number}")


def _next_order_index(db: Session) -> int:
    mx = db.scalar(select(func.max(QueueItem.order_index)))
    return (mx + 1) if mx is not None else 0


def create_run(
    db: Session,
    ticket: Ticket,
    persona: str,
    agent: str,
    model: str,
    skills: list[str] | None,
    review_comment: str | None = None,
    previous_output_path: str | None = None,
) -> AgentRun:
    run_number = next_run_number(db, ticket)
    output_path = compute_output_path(ticket, agent, run_number)
    run = AgentRun(
        ticket_id=ticket.id, run_number=run_number, agent=agent, model=model,
        persona=persona, skills_json=list(skills or []), plugins_json=[],
        output_path=output_path, status="queued",
    )
    db.add(run)
    db.flush()  # assign run.id before building the prompt (it embeds run_id)

    run.prompt_md = prompt_builder.build_prompt(
        ticket, run_id=run.id, run_number=run_number, persona=persona, agent=agent,
        model=model, skills=list(skills or []), output_path=output_path,
        review_comment=review_comment, previous_output_path=previous_output_path,
    )
    db.add(QueueItem(ticket_id=ticket.id, run_id=run.id, order_index=_next_order_index(db), state="queued"))
    db.flush()
    return run
