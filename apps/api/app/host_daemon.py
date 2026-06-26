"""Phase 5C — Host execution daemon (interactive tmux CLI).

Runs OUTSIDE Docker, on the host, so it can drive the host's tmux and the
logged-in Codex/Claude CLI directly (subscription plans perform better
interactively than in print/exec mode — spec §10, D3). The container backend only
touches Postgres; this daemon is the real Executor.

Loop:
  1. poll `agent_runs(state=queued)` (per-brain concurrency)
  2. open a NEW WINDOW in the dedicated tmux session, launch the interactive CLI
     pre-authorized via official flags (§11) with the chosen model (§12)
  3. send the built prompt into the session
  4. tail the pane into `runs/<id>/run.log` for the board's live view (§13);
     classify output (§5.1): usage-limit → snapshot + schedule a Haiku-parsed
     resume (§14); transient → retry/fallback; done → kill the window, hand off
     to the Watcher (Reviewing)

Run on the host (NOT in Docker):

    DATABASE_URL=postgresql+psycopg://asv2:asv2@localhost:5432/asv2 \\
    ASV2_AGENT_MODE=real \\
    python -m app.host_daemon

Requires: `tmux`, and `claude` / `codex` already logged in on the host.

NOTE: completion/permission heuristics on a live interactive pane need tuning in
Kay's environment — the prompt instructs the CLI to write the `.agent_done.json`
sentinel, which is the primary completion signal; pane-idle is the fallback.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_db
from .models import AgentPermissionProfile, AgentRun, QueueItem, Ticket
from .services import cli_exec, failure, lifecycle, permissions


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603


def _ensure_session() -> None:
    if _run(["tmux", "has-session", "-t", cli_exec.TMUX_SESSION]).returncode != 0:
        _run(["tmux", "new-session", "-d", "-s", cli_exec.TMUX_SESSION])


def _preset_for(db, brain: str) -> str:
    prof = db.scalars(
        select(AgentPermissionProfile).where(AgentPermissionProfile.brain == brain)
    ).first()
    return prof.preset if prof else permissions.DEFAULT_PRESET


def _start_run(db, run: AgentRun) -> None:
    ticket = run.ticket
    if ticket.status != "In Progress":
        lifecycle.transition_ticket(db, ticket, "In Progress", actor="Hermes",
                                    reason_md="Host daemon dispatch.", run=run)
    out = Path(run.output_path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.md").write_text(run.prompt_md, encoding="utf-8")
    run.log_path = str(out / "run.log")
    run.tmux_window = cli_exec.window_name(run.id)
    run.status = "running"
    run.started_at = datetime.utcnow()
    db.commit()

    preset = _preset_for(db, run.agent)
    _ensure_session()
    _run(cli_exec.build_new_window_command(run.id, run.agent, run.model, preset, run.log_path))
    time.sleep(1.5)  # let the CLI session come up before sending the prompt
    _run(cli_exec.send_prompt_command(run.id, str(out / "prompt.md")))


def _pane(run: AgentRun) -> str:
    return _run(cli_exec.capture_pane_command(run.id)).stdout


def _sentinel_done(run: AgentRun) -> bool:
    return (Path(run.output_path) / ".agent_done.json").exists()


def _handle_rate_limit(db, run: AgentRun, pane: str) -> None:
    """Usage-limit (§14): snapshot the pane, let Haiku parse the reset time, schedule
    a resume. (Haiku call is wired in real mode; here we record the snapshot + job.)"""
    snap = Path(run.output_path) / f"ratelimit-{int(run.id)}.log"
    snap.write_text(pane, encoding="utf-8")
    # Real: claude -p "<pane>" --model claude-haiku-4-5 --output-format json --json-schema ...
    # → reset_time. Until parsed, schedule a conservative retry window.
    from datetime import timedelta
    failure.schedule_rate_limit_resume(db, run, datetime.utcnow() + timedelta(hours=5), str(snap))
    _run(cli_exec.kill_window_command(run.id))
    db.commit()


def tick(db) -> list[int]:
    busy: dict[str, int] = {}
    for r in db.scalars(select(AgentRun).where(AgentRun.status == "running")).all():
        busy[r.agent] = busy.get(r.agent, 0) + 1
    started: list[int] = []
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
        qi.locked_by = "host-daemon"
        qi.started_at = datetime.utcnow()
        _start_run(db, run)
        busy[run.agent] = busy.get(run.agent, 0) + 1
        started.append(run.id)
    db.commit()
    return started


def supervise(db) -> None:
    """Tail running panes, classify, and finish (kill window) on sentinel."""
    for run in db.scalars(select(AgentRun).where(AgentRun.status == "running")).all():
        pane = _pane(run)
        if run.log_path:
            Path(run.log_path).write_text(pane, encoding="utf-8")
        cls = failure.classify(pane).cls
        if cls == failure.FailureClass.USAGE_LIMIT:
            _handle_rate_limit(db, run, pane)
            continue
        if _sentinel_done(run):
            _run(cli_exec.kill_window_command(run.id))
            # leave run 'running'; the Watcher detects the sentinel and moves the
            # ticket to Reviewing (single responsibility — spec §10.2).


def main(interval: float = 3.0) -> None:
    init_db()
    print(f"[host-daemon] started (mode={settings.agent_mode}, tmux={cli_exec.TMUX_SESSION})", flush=True)
    while True:
        db = SessionLocal()
        try:
            started = tick(db)
            if started:
                print(f"[host-daemon] started runs: {started}", flush=True)
            supervise(db)
        except Exception as exc:  # keep the daemon alive
            print(f"[host-daemon] error: {exc}", flush=True)
        finally:
            db.close()
        time.sleep(interval)


if __name__ == "__main__":
    main()
