"""LLM Wiki raw-event writer.

Every status change writes an append-only markdown file under the canonical
wiki raw path. The DB is the source of truth; raw files feed search/RAG.
"""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import NavigatorDecision, StatusEvent, Ticket


def _raw_dir() -> Path:
    d = Path(settings.llm_wiki_root) / settings.wiki_raw_subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "event"


def _kst(dt) -> str:
    if dt is None:
        return ""
    return (dt + timedelta(hours=settings.tz_offset_hours)).strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def _yaml_list(items: list[str]) -> str:
    if not items:
        return " []"
    return "\n" + "\n".join(f"  - {i}" for i in items)


def write_status_event(db: Session, ticket: Ticket, event: StatusEvent, run=None) -> str:
    """Write one raw markdown event file and return its absolute path."""
    nav = db.scalars(
        select(NavigatorDecision)
        .where(NavigatorDecision.ticket_id == ticket.id)
        .order_by(NavigatorDecision.created_at.desc())
    ).first()

    persona = (run.persona if run else None) or ticket.assignee_persona or (nav.persona if nav else "")
    agent = (run.agent if run else None) or (nav.agent if nav else "")
    model = (run.model if run else None) or (nav.model if nav else "")
    artifacts = [a.path for a in run.artifacts] if run else []

    fm = [
        "---",
        "type: agent_ticket_event",
        f"ticket_id: {ticket.id}",
        f"ticket_number: {ticket.ticket_number}",
        f"status_from: {event.from_status or 'null'}",
        f"status_to: {event.to_status}",
        f"actor: {event.actor}",
        f"persona: {persona or 'null'}",
        f"agent: {agent or 'null'}",
        f"model: {model or 'null'}",
        f"run_id: {run.id if run else 'null'}",
        f"artifacts:{_yaml_list(artifacts)}",
        f"created_at: {_kst(event.created_at)}",
        "---",
        "",
    ]

    comments = ticket.comments[-5:]
    comment_block = "\n\n".join(
        f"- **{c.author_name or c.author_type}** ({c.author_type}): {c.body_md}" for c in comments
    ) or "_No comments._"

    result_summary = "_No run associated._"
    if run:
        parts = [f"- run #{run.run_number} · status: **{run.status}**"]
        if run.error:
            parts.append(f"- error: {run.error}")
        for a in run.artifacts:
            if a.summary:
                parts.append(f"- {Path(a.path).name}: {a.summary}")
        result_summary = "\n".join(parts)

    artifact_block = "\n".join(f"- `{p}`" for p in artifacts) or "_None._"

    body = [
        f"# {ticket.ticket_number} status change: {event.from_status or '(new)'} → {event.to_status}",
        "",
        "## Ticket",
        f"**{ticket.title}**",
        "",
        ticket.description_md or "_No description._",
        "",
        "### Acceptance Criteria",
        ticket.acceptance_criteria_md or "_None._",
        "",
        "## Decision / Reason",
        event.reason_md or (f"Navigator: {nav.reason}" if nav else "_No reason recorded._"),
        "",
        "## Comments / Review",
        comment_block,
        "",
        "## Result Summary",
        result_summary,
        "",
        "## Artifacts",
        artifact_block,
        "",
    ]

    fname = f"{ticket.ticket_number}-evt{event.id:04d}-{_slug(event.to_status)}.md"
    path = _raw_dir() / fname
    path.write_text("\n".join(fm) + "\n".join(body), encoding="utf-8")
    return str(path)


def fork_raw(db: Session, ticket: Ticket, note_md: str | None) -> str:
    """Manual raw note fork (POST /wiki-sync/.../fork-raw)."""
    from datetime import datetime

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    fm = [
        "---",
        "type: agent_ticket_note",
        f"ticket_id: {ticket.id}",
        f"ticket_number: {ticket.ticket_number}",
        f"status: {ticket.status}",
        f"created_at: {_kst(datetime.utcnow())}",
        "---",
        "",
        f"# {ticket.ticket_number} note",
        "",
        note_md or "_(manual fork)_",
        "",
    ]
    path = _raw_dir() / f"{ticket.ticket_number}-note-{ts}.md"
    path.write_text("\n".join(fm), encoding="utf-8")
    return str(path)
