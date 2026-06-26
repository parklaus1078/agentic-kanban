"""Phase 3 — data durability / fail-safe.

This machine loses its WSL instance, Docker containers and tmux sessions to power
cuts. We keep state recoverable two ways:

1. **Snapshots** — dump the container Postgres to ``/mnt/k`` (outside WSL) on a
   schedule, pruning to the most recent N. On boot, if the DB came up empty, the
   latest snapshot can be restored. (PGDATA is NOT run on drvfs — see the spec.)
2. **Run recovery** — a run that was mid-flight when the power dropped is left
   stuck in ``dispatched``/``running`` with its tmux window gone. On boot we
   re-queue it so the worker picks it up again (runs are idempotent).

``pg_dump`` only applies to Postgres; on the SQLite dev/test DB the snapshot is a
no-op so the rest of the fail-safe logic stays unit-testable.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AgentRun, QueueItem

SNAPSHOT_PREFIX = "asv2-"
SNAPSHOT_SUFFIX = ".sql"


def _is_postgres() -> bool:
    return settings.database_url.startswith("postgres")


def _libpq_url() -> str:
    """pg_dump wants a libpq URL; strip SQLAlchemy's ``+psycopg`` driver tag."""
    return settings.database_url.replace("postgresql+psycopg", "postgresql")


def list_snapshots(out_dir: str | None = None) -> list[str]:
    d = Path(out_dir or settings.snapshot_dir)
    if not d.exists():
        return []
    return sorted(str(p) for p in d.glob(f"{SNAPSHOT_PREFIX}*{SNAPSHOT_SUFFIX}"))


def prune_snapshots(keep: int | None = None, out_dir: str | None = None) -> list[str]:
    keep = settings.snapshot_keep if keep is None else keep
    snaps = list_snapshots(out_dir)
    doomed = snaps[:-keep] if keep > 0 else snaps
    removed: list[str] = []
    for p in doomed:
        try:
            os.remove(p)
            removed.append(p)
        except OSError:
            pass
    return removed


def create_snapshot(stamp: str, out_dir: str | None = None, runner=subprocess.run) -> str | None:
    """Dump the live Postgres DB to ``out_dir/asv2-<stamp>.sql``. Returns the path,
    or ``None`` when the DB is not Postgres (nothing to fail-safe there)."""
    if not _is_postgres():
        return None
    d = Path(out_dir or settings.snapshot_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{SNAPSHOT_PREFIX}{stamp}{SNAPSHOT_SUFFIX}"
    runner(["pg_dump", "--no-owner", "--dbname", _libpq_url(), "--file", str(out)], check=True)
    return str(out)


def recover_interrupted_runs(db: Session) -> int:
    """Re-queue runs that were executing when the process died. Idempotent."""
    stuck = db.scalars(
        select(AgentRun).where(AgentRun.status.in_(("dispatched", "running")))
    ).all()
    for run in stuck:
        run.status = "queued"
        run.process_id = None
        run.started_at = None
        qi = db.scalars(select(QueueItem).where(QueueItem.run_id == run.id)).first()
        if qi is not None:
            if qi.state == "running":
                qi.state = "queued"
                qi.locked_by = None
        else:
            db.add(QueueItem(ticket_id=run.ticket_id, run_id=run.id, order_index=0, state="queued"))
    if stuck:
        db.commit()
    return len(stuck)
