"""Phase 6 — recursive ticket subdivision (spec §8).

Kay triggers subdivision on a ticket → the Navigator routes a planning persona
(PM/CTO) → a proposal of child tickets is generated → Kay approves → children are
created in Todo with ``parent_ticket_id`` set. Children can themselves be
subdivided (recursive). When every child of a parent reaches Completed and the
parent has ``auto_complete_parent`` on (default), the parent auto-completes
(rolling up recursively).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import seed, transitions as T
from ..models import StatusBlock, SubdivisionProposal, Ticket
from . import lifecycle, navigator

_PROJECT_HINTS = ("app", "system", "platform", "build", "project", "service", "website", "api")


def _propose_children(ticket: Ticket) -> list[dict]:
    ctx = f"{ticket.title} {ticket.description_md or ''}".lower()
    if any(k in ctx for k in _PROJECT_HINTS):
        parts = ["Backend (BE)", "Frontend (FE)", "Database (DB)", "Infra & deploy", "System design"]
    else:
        parts = ["Plan & spec", "Implement", "Test & verify"]
    return [
        {
            "title": f"{ticket.title} — {p}",
            "description_md": f"Subtask **{p}** of {ticket.ticket_number}: {ticket.title}",
            "acceptance_criteria_md": "",
        }
        for p in parts
    ]


def propose(db: Session, ticket: Ticket, created_by: str = "Navigator") -> SubdivisionProposal:
    # Record the planning-routing decision (persona/skills) for traceability.
    navigator.recommend(db, ticket, None, task_kind="subdivide")
    proposal = SubdivisionProposal(
        parent_ticket_id=ticket.id,
        proposed_children_json=_propose_children(ticket),
        status="proposed",
        created_by=created_by,
    )
    db.add(proposal)
    db.flush()
    return proposal


def approve(db: Session, proposal: SubdivisionProposal) -> list[Ticket]:
    parent = db.get(Ticket, proposal.parent_ticket_id)
    todo = db.scalars(
        select(StatusBlock).where(StatusBlock.board_id == parent.board_id, StatusBlock.name == T.TODO)
    ).first()
    children: list[Ticket] = []
    for spec in proposal.proposed_children_json:
        child = Ticket(
            board_id=parent.board_id,
            ticket_number=seed.next_ticket_number(db),
            title=spec["title"],
            description_md=spec.get("description_md", ""),
            acceptance_criteria_md=spec.get("acceptance_criteria_md", ""),
            status_block_id=todo.id,
            parent_ticket_id=parent.id,
        )
        db.add(child)
        db.flush()
        children.append(child)
    proposal.status = "approved"
    db.flush()
    return children


def reject(db: Session, proposal: SubdivisionProposal) -> SubdivisionProposal:
    proposal.status = "rejected"
    db.flush()
    return proposal


def maybe_autocomplete_parent(db: Session, child: Ticket) -> bool:
    """If every sibling is Completed and the parent opts in, complete the parent
    (rolling up recursively). Uses enforce=False: this is a system rollup, not a
    normal workflow edge."""
    if child.parent_ticket_id is None:
        return False
    parent = db.get(Ticket, child.parent_ticket_id)
    if parent is None or not parent.auto_complete_parent or parent.status in T.TERMINAL:
        return False
    # Compare status_block_id (a column, always fresh after flush) rather than the
    # .status relationship, which can be stale for a sibling just transitioned in
    # this same session.
    completed = db.scalars(
        select(StatusBlock).where(StatusBlock.board_id == parent.board_id, StatusBlock.name == T.COMPLETED)
    ).first()
    siblings = db.scalars(select(Ticket).where(Ticket.parent_ticket_id == parent.id)).all()
    if siblings and completed and all(s.status_block_id == completed.id for s in siblings):
        lifecycle.transition_ticket(
            db, parent, T.COMPLETED, actor="Orchestrator",
            reason_md="All child tickets completed.", enforce=False,
        )
        maybe_autocomplete_parent(db, parent)  # recurse up the tree
        return True
    return False
