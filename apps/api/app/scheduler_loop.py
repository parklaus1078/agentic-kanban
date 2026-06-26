"""LLM Wiki ingest/audit scheduler.

- ingest: daily 02:00 Asia/Seoul — mark pending wiki sync jobs ingested + refresh an index.
- audit:  month-end 04:00 Asia/Seoul — verify raw files exist and events have raw paths.

Usable three ways:
  python -m app.scheduler_loop          # long-running scheduler
  python -m app.scheduler_loop ingest   # run ingest once (for cron)
  python -m app.scheduler_loop audit    # run audit once (for cron)
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, init_db
from .models import StatusEvent, WikiSyncJob
from .services import durability


def _raw_dir() -> Path:
    return Path(settings.llm_wiki_root) / settings.wiki_raw_subdir


def ingest(db: Session) -> int:
    pending = db.scalars(select(WikiSyncJob).where(WikiSyncJob.ingest_status == "pending")).all()
    ingested = 0
    for job in pending:
        if Path(job.raw_path).exists():
            job.ingest_status = "ingested"
            job.completed_at = datetime.utcnow()
            ingested += 1
        else:
            job.ingest_status = "missing"
    db.commit()

    files = sorted(p.name for p in _raw_dir().glob("*.md") if not p.name.startswith("_"))
    index = ["# Agent System v2 — raw event index", "",
             f"Generated (ingest): {(datetime.utcnow() + timedelta(hours=9)).isoformat()}+09:00",
             f"Total raw files: {len(files)}", ""]
    index += [f"- {f}" for f in files]
    (_raw_dir() / "_index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"[scheduler] ingest: {ingested} job(s) ingested, {len(files)} raw files indexed", flush=True)
    return ingested


def audit(db: Session) -> dict:
    jobs = db.scalars(select(WikiSyncJob)).all()
    missing_files = 0
    for job in jobs:
        if Path(job.raw_path).exists():
            job.audit_status = "ok"
        else:
            job.audit_status = "missing"
            missing_files += 1
    events = db.scalars(select(StatusEvent)).all()
    events_without_raw = sum(1 for e in events if not e.wiki_raw_path)
    db.commit()
    summary = {
        "jobs": len(jobs),
        "missing_raw_files": missing_files,
        "status_events": len(events),
        "events_without_raw_path": events_without_raw,
    }
    print(f"[scheduler] audit: {summary}", flush=True)
    return summary


def snapshot_once() -> str | None:
    """Phase 3: dump Postgres to /mnt/k and prune. No-op on SQLite."""
    stamp = (datetime.utcnow() + timedelta(hours=settings.tz_offset_hours)).strftime(
        "%Y%m%d-%H%M%S"
    )
    path = durability.create_snapshot(stamp)
    durability.prune_snapshots()
    print(f"[scheduler] snapshot: {path or 'skipped (non-postgres)'}", flush=True)
    return path


def _run_once(which: str) -> None:
    init_db()
    if which == "snapshot":
        snapshot_once()
        return
    db = SessionLocal()
    try:
        ingest(db) if which == "ingest" else audit(db)
    finally:
        db.close()


def main() -> None:
    init_db()
    print(
        "[scheduler] started (ingest 02:00 KST, audit 04:00 KST month-end, "
        f"snapshot every {settings.snapshot_interval_minutes}m)",
        flush=True,
    )
    last_ingest_day = ""
    last_audit_day = ""
    last_snapshot_ts = 0.0
    while True:
        kst = datetime.utcnow() + timedelta(hours=settings.tz_offset_hours)
        day = kst.strftime("%Y-%m-%d")
        is_month_end = (kst + timedelta(days=1)).month != kst.month
        db = SessionLocal()
        try:
            if kst.hour == 2 and last_ingest_day != day:
                ingest(db)
                last_ingest_day = day
            if is_month_end and kst.hour == 4 and last_audit_day != day:
                audit(db)
                last_audit_day = day
        except Exception as exc:
            print(f"[scheduler] error: {exc}", flush=True)
        finally:
            db.close()
        # Periodic durability snapshot (Phase 3).
        if settings.snapshot_interval_minutes > 0:
            now = time.monotonic()
            if now - last_snapshot_ts >= settings.snapshot_interval_minutes * 60:
                try:
                    snapshot_once()
                except Exception as exc:
                    print(f"[scheduler] snapshot error: {exc}", flush=True)
                last_snapshot_ts = now
        time.sleep(30)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"ingest", "audit", "snapshot"}:
        _run_once(sys.argv[1])
    else:
        main()
