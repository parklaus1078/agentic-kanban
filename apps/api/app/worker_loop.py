"""Standalone worker loop (`python -m app.worker_loop`).

Polls the queue and starts eligible runs. Each plan is one session/worker for the
MVP; concurrency is bounded by ASV2_MAX_CONCURRENCY_PER_AGENT.
"""
from __future__ import annotations

import time

from .config import settings
from .db import SessionLocal, init_db
from .services import adapter


def main(interval: float = 3.0) -> None:
    init_db()
    print(f"[worker] started (agent_mode={settings.agent_mode}, interval={interval}s)", flush=True)
    while True:
        db = SessionLocal()
        try:
            started = adapter.worker_tick(db)
            if started:
                print(f"[worker] started runs: {started}", flush=True)
        except Exception as exc:  # keep the loop alive
            print(f"[worker] error: {exc}", flush=True)
        finally:
            db.close()
        time.sleep(interval)


if __name__ == "__main__":
    main()
