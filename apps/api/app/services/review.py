"""Kay review decision: satisfied -> Completed; not satisfied -> rerun loop.

On rerun the review comment is recorded and embedded into the next run's prompt
(via runs.create_run(review_comment=...)), satisfying the rerun_context requirement.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import transitions as T
from ..models import AgentRun, Comment, Ticket
from . import lifecycle, runs


def review_ticket(
    db: Session, ticket: Ticket, satisfied: bool, comment_md: str | None, actor: str = "Kay"
) -> tuple[Ticket, AgentRun | None]:
    body = comment_md or ("Approved." if satisfied else "Not satisfied — please rerun.")
    db.add(Comment(ticket_id=ticket.id, author_type="kay", author_name=actor,
                   body_md=body, is_digestible=True))
    db.flush()

    if satisfied:
        lifecycle.transition_ticket(db, ticket, T.COMPLETED, actor=actor,
                                    reason_md=comment_md or "Approved by Kay.")
        db.commit()
        db.refresh(ticket)
        return ticket, None

    # Not satisfied: send back to In Progress and create a rerun carrying the comment.
    lifecycle.transition_ticket(db, ticket, T.IN_PROGRESS, actor=actor,
                                reason_md=f"Rerun requested by Kay: {body}")
    prev = db.scalars(
        select(AgentRun).where(AgentRun.ticket_id == ticket.id).order_by(AgentRun.run_number.desc())
    ).first()
    persona = prev.persona if prev else (ticket.assignee_persona or "Full Stack Developer")
    agent = prev.agent if prev else "claude"
    model = prev.model if prev else "Claude CLI Sonnet 4.6"
    skills = (prev.skills_json if prev else []) or []
    prev_output = prev.output_path if prev else None

    rerun = runs.create_run(db, ticket, persona, agent, model, skills,
                            review_comment=body, previous_output_path=prev_output)
    db.commit()
    db.refresh(ticket)
    db.refresh(rerun)
    return ticket, rerun
