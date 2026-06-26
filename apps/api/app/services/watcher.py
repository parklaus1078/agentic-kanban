"""Watcher tick — detect run completion and move tickets to Reviewing/Blocked.

Detection signals: sentinel file (`.agent_done.json`), output-path scan, and
timeout. On success the watcher creates artifact rows + watcher events, marks the
run success, and transitions the ticket to Reviewing (writing the wiki raw event).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import transitions as T
from ..config import settings
from ..models import AgentRun, Artifact, QueueItem, WatcherEvent
from . import lifecycle

_MIME = {".md": "text/markdown", ".json": "application/json", ".txt": "text/plain",
         ".py": "text/x-python", ".csv": "text/csv", ".html": "text/html"}


def _mime(path: str) -> str:
    return _MIME.get(Path(path).suffix.lower(), "application/octet-stream")


def _checksum(path: str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _event(db: Session, run: AgentRun, event_type: str, payload: dict) -> None:
    db.add(WatcherEvent(run_id=run.id, event_type=event_type, payload_json=payload,
                        observed_at=datetime.utcnow()))


def _close_queue_item(db: Session, run: AgentRun, state: str) -> None:
    qi = db.scalars(select(QueueItem).where(QueueItem.run_id == run.id)).first()
    if qi:
        qi.state = state


def _complete_run(db: Session, run: AgentRun, sentinel: dict) -> None:
    _event(db, run, "sentinel_detected", sentinel)
    status = sentinel.get("status", "success")
    author = sentinel.get("author_name", run.persona)
    summary = sentinel.get("summary", "")

    for path in sentinel.get("artifacts", []):
        db.add(Artifact(run_id=run.id, path=path, mime_type=_mime(path),
                        author_name=author, summary=summary, checksum=_checksum(path)))
    db.flush()  # so run.artifacts is populated for the wiki event

    run.finished_at = datetime.utcnow()
    if status == "success":
        run.status = "success"
        _close_queue_item(db, run, "done")
        _event(db, run, "completed", {"status": "success", "artifacts": len(sentinel.get("artifacts", []))})
        lifecycle.transition_ticket(db, run.ticket, T.REVIEWING, actor="Watcher",
                                    reason_md=summary or "Agent run completed.", run=run, enforce=False)
    else:
        run.status = "failed"
        run.error = sentinel.get("error", "agent reported failure")
        _close_queue_item(db, run, "done")
        _event(db, run, "failed", {"status": "failed", "error": run.error})
        lifecycle.transition_ticket(db, run.ticket, T.BLOCKED, actor="Watcher",
                                    reason_md=run.error, run=run, enforce=False)


def _pid_alive(process_id: str | None) -> bool:
    """Real process liveness. Simulated runs ('sim-*') are driven by the sentinel,
    so they are always treated as alive here."""
    if not process_id or process_id.startswith("sim-"):
        return True
    try:
        os.kill(int(process_id), 0)
        return True
    except ProcessLookupError:
        return False
    except (ValueError, PermissionError):
        return True  # can't determine -> assume still running


def _process_exit_run(db: Session, run: AgentRun) -> None:
    """A real CLI process exited without leaving a sentinel -> incomplete -> Blocked."""
    run.status = "failed"
    run.finished_at = datetime.utcnow()
    run.error = "process exited without writing .agent_done.json"
    _event(db, run, "process_exit", {"process_id": run.process_id})
    _close_queue_item(db, run, "done")
    lifecycle.transition_ticket(db, run.ticket, T.BLOCKED, actor="Watcher",
                                reason_md=run.error, run=run, enforce=False)


def _timeout_run(db: Session, run: AgentRun) -> None:
    run.status = "failed"
    run.finished_at = datetime.utcnow()
    run.error = f"timeout after {settings.run_timeout_seconds}s"
    _event(db, run, "timeout", {"timeout_seconds": settings.run_timeout_seconds})
    _close_queue_item(db, run, "done")
    lifecycle.transition_ticket(db, run.ticket, T.BLOCKED, actor="Watcher",
                                reason_md=run.error, run=run, enforce=False)


def watcher_tick(db: Session) -> list[int]:
    detected: list[int] = []
    now = datetime.utcnow()
    for run in db.scalars(select(AgentRun).where(AgentRun.status == "running")).all():
        out = Path(run.output_path) if run.output_path else None
        sentinel = (out / ".agent_done.json") if out else None
        if sentinel and sentinel.exists():
            try:
                data = json.loads(sentinel.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {"status": "failed", "error": "unreadable sentinel"}
            _complete_run(db, run, data)
            detected.append(run.id)
        elif not _pid_alive(run.process_id):
            _process_exit_run(db, run)
            detected.append(run.id)
        elif run.started_at and (now - run.started_at).total_seconds() > settings.run_timeout_seconds:
            _timeout_run(db, run)
            detected.append(run.id)
        elif out and out.exists():
            # output-path scan: note progress files even before the sentinel lands
            files = [p.name for p in out.iterdir() if p.name not in {".agent_done.json", "prompt.md"}]
            if files:
                _event(db, run, "output_scan", {"files": files})

    db.commit()
    return detected
