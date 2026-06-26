"""Phase 4 — LangGraph orchestration (spec §5).

The board lifecycle modelled as an explicit StateGraph:

    navigate → dispatch → (failure policy) → watch → END

- **navigate**: the Navigator picks persona / agent / model / skills.
- **dispatch**: reuse the queued run the drag already enqueued (or create one),
  then run it. Classify the output (§5.1).
- conditional edges: ``transient`` → retry (bounded) → fallback; ``usage_limit`` →
  schedule a resume (§14) and end; otherwise → watch.
- **watch**: detect completion and move the ticket to Reviewing/Blocked.

This *wraps* the existing services (navigator/runs/adapter/watcher) so the working
end-to-end flow is preserved — the polling worker/watcher remain the execution
substrate. Checkpointer is MemorySaver for the MVP/tests (spec §25 open question;
Postgres via ``langgraph-checkpoint-postgres`` is the production target).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from .. import transitions as T
from ..db import SessionLocal
from ..models import AgentRun, Ticket
from . import adapter, failure, lifecycle, navigator, runs, watcher

MAX_RETRIES = 3


class OrchState(TypedDict, total=False):
    ticket_id: int
    run_id: int | None
    persona: str
    agent: str
    model: str
    skills: list
    failure_cls: str
    retries: int


def _navigate(state: OrchState) -> dict:
    db = SessionLocal()
    try:
        ticket = db.get(Ticket, state["ticket_id"])
        d = navigator.recommend(db, ticket, None)
        out = {"persona": d.persona, "agent": d.agent, "model": d.model, "skills": list(d.skills_json or [])}
        db.commit()
        return out
    finally:
        db.close()


def _dispatch(state: OrchState) -> dict:
    db = SessionLocal()
    try:
        ticket = db.get(Ticket, state["ticket_id"])
        run = db.scalars(
            select(AgentRun).where(AgentRun.ticket_id == ticket.id, AgentRun.status == "queued")
        ).first()
        if run is None:
            run = runs.create_run(
                db, ticket, state["persona"], state["agent"], state["model"], state.get("skills", [])
            )
        db.commit()
        run_id = run.id
        # Execute via the existing worker tick (simulated writes the sentinel).
        adapter.worker_tick(db)
        db.refresh(run)
        fcls = failure.classify(run.error or "").cls
        return {"run_id": run_id, "failure_cls": fcls}
    finally:
        db.close()


def route_after_dispatch(state: OrchState) -> str:
    fc = state.get("failure_cls", failure.FailureClass.NONE)
    if fc == failure.FailureClass.USAGE_LIMIT:
        return "rate_limited"
    if fc == failure.FailureClass.TRANSIENT:
        return "retry" if state.get("retries", 0) < MAX_RETRIES else "blocked"
    return "watch"


def _retry(state: OrchState) -> dict:
    return {"retries": state.get("retries", 0) + 1}


def _watch(state: OrchState) -> dict:
    db = SessionLocal()
    try:
        watcher.watcher_tick(db)
        return {}
    finally:
        db.close()


def _rate_limited(state: OrchState) -> dict:
    db = SessionLocal()
    try:
        run = db.get(AgentRun, state.get("run_id")) if state.get("run_id") else None
        if run is not None:
            # No precise reset in simulated mode; use a conservative window.
            failure.schedule_rate_limit_resume(db, run, datetime.utcnow() + timedelta(hours=5))
            db.commit()
        return {}
    finally:
        db.close()


def _blocked(state: OrchState) -> dict:
    db = SessionLocal()
    try:
        ticket = db.get(Ticket, state["ticket_id"])
        if ticket and ticket.status not in T.TERMINAL and ticket.status != T.BLOCKED:
            lifecycle.transition_ticket(db, ticket, T.BLOCKED, actor="Orchestrator",
                                        reason_md="Run failed after retries/fallback.")
            db.commit()
        return {}
    finally:
        db.close()


def build_graph():
    g = StateGraph(OrchState)
    g.add_node("navigate", _navigate)
    g.add_node("dispatch", _dispatch)
    g.add_node("retry", _retry)
    g.add_node("watch", _watch)
    g.add_node("rate_limited", _rate_limited)
    g.add_node("blocked", _blocked)
    g.add_edge(START, "navigate")
    g.add_edge("navigate", "dispatch")
    g.add_conditional_edges(
        "dispatch",
        route_after_dispatch,
        {"watch": "watch", "retry": "retry", "rate_limited": "rate_limited", "blocked": "blocked"},
    )
    g.add_edge("retry", "dispatch")
    g.add_edge("watch", END)
    g.add_edge("rate_limited", END)
    g.add_edge("blocked", END)
    return g.compile(checkpointer=MemorySaver())


def run_ticket(ticket_id: int) -> dict:
    """Drive one ticket through the lifecycle graph (simulated execution)."""
    graph = build_graph()
    return graph.invoke(
        {"ticket_id": ticket_id, "retries": 0},
        config={"configurable": {"thread_id": f"ticket-{ticket_id}"}},
    )
