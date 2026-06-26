"""Agent adapter + worker tick.

The worker dequeues queued runs (respecting per-agent concurrency), marks the
ticket In Progress, then executes the adapter. The adapter has two modes:
  - simulated (default): writes a deterministic artifact + `.agent_done.json`
    sentinel so the Watcher can be tested without spending model quota.
  - real: spawns the configured CLI (Codex/Claude) as a subprocess; that CLI is
    expected to write the sentinel itself.
The worker does NOT mark the run finished — detection is the Watcher's job.
"""
from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import transitions as T
from ..config import settings
from ..models import AgentRun, QueueItem
from . import lifecycle


def _write_simulated_output(run: AgentRun) -> dict:
    out = Path(run.output_path)
    out.mkdir(parents=True, exist_ok=True)
    ticket = run.ticket
    result = out / "result.md"
    result.write_text(
        f"# {ticket.ticket_number} — deliverable (run #{run.run_number})\n\n"
        f"Persona: **{run.persona}** · Agent: **{run.agent}** · Model: **{run.model}**\n\n"
        f"## Task\n{ticket.title}\n\n"
        f"{ticket.description_md or '_no description_'}\n\n"
        f"## Acceptance criteria addressed\n{ticket.acceptance_criteria_md or '_none_'}\n\n"
        f"## Skills applied\n" + ("\n".join(f"- {s}" for s in run.skills_json) or "- (none)") + "\n\n"
        f"## Notes\nThis is a SIMULATED deliverable produced by the worker adapter so the\n"
        f"full lifecycle (worker -> watcher -> review) can be demonstrated deterministically.\n",
        encoding="utf-8",
    )
    sentinel = {
        "run_id": run.id,
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "agent": run.agent,
        "model": run.model,
        "persona": run.persona,
        "status": "success",
        "summary": f"Produced result.md for {ticket.ticket_number} as {run.persona}.",
        "artifacts": [str(result)],
        "author_name": run.persona,
        "finished_at": datetime.utcnow().isoformat() + "Z",
    }
    (out / ".agent_done.json").write_text(json.dumps(sentinel, indent=2), encoding="utf-8")
    return sentinel


def _spawn_real(run: AgentRun) -> str | None:
    """Best-effort real CLI spawn. Returns a process id string, or None on failure."""
    out = Path(run.output_path)
    out.mkdir(parents=True, exist_ok=True)
    prompt_file = out / "prompt.md"
    template = settings.codex_cmd_template if run.agent == "codex" else settings.claude_cmd_template
    if not template:
        return None
    cmd = template.format(prompt_file=str(prompt_file), output_dir=str(out))
    try:
        proc = subprocess.Popen(shlex.split(cmd), cwd=str(out))  # noqa: S603
        return str(proc.pid)
    except Exception as exc:  # pragma: no cover - environment dependent
        run.error = f"real adapter spawn failed: {exc}"
        return None


def execute_run(db: Session, run: AgentRun) -> None:
    ticket = run.ticket
    if ticket.status != T.IN_PROGRESS:
        lifecycle.transition_ticket(
            db, ticket, T.IN_PROGRESS, actor="Hermes",
            reason_md="Auto-started by worker on run dispatch.", run=run,
        )

    out = Path(run.output_path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.md").write_text(run.prompt_md, encoding="utf-8")

    run.status = "running"
    run.started_at = datetime.utcnow()

    if settings.agent_mode == "real":
        pid = _spawn_real(run)
        if pid:
            run.process_id = pid
        else:  # fall back to simulated so the lifecycle still completes
            run.process_id = f"sim-{run.id}"
            _write_simulated_output(run)
    else:
        run.process_id = f"sim-{run.id}"
        _write_simulated_output(run)

    db.flush()


def worker_tick(db: Session) -> list[int]:
    """Start eligible queued runs (one per agent up to max concurrency). Returns started run ids."""
    busy: dict[str, int] = {}
    for r in db.scalars(select(AgentRun).where(AgentRun.status == "running")).all():
        busy[r.agent] = busy.get(r.agent, 0) + 1

    processed: list[int] = []
    queued = db.scalars(
        select(QueueItem).where(QueueItem.state == "queued").order_by(QueueItem.order_index)
    ).all()
    for qi in queued:
        if qi.cancel_requested or qi.run_id is None:
            continue
        run = db.get(AgentRun, qi.run_id)
        if run is None or run.status != "queued":
            continue
        if busy.get(run.agent, 0) >= settings.max_concurrency_per_agent:
            continue
        qi.state = "running"
        qi.locked_by = "worker"
        qi.started_at = datetime.utcnow()
        execute_run(db, run)
        busy[run.agent] = busy.get(run.agent, 0) + 1
        processed.append(run.id)

    db.commit()
    return processed
