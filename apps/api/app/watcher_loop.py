"""Standalone watcher loop (`python -m app.watcher_loop`).

Polls running runs for sentinel files / output / timeout and transitions tickets
to Reviewing (success) or Blocked (failure).
"""
from __future__ import annotations

import time

from .db import SessionLocal, init_db
from .services import watcher


def main(interval: float = 2.0) -> None:
    init_db()
    print(f"[watcher] started (interval={interval}s)", flush=True)
    while True:
        db = SessionLocal()
        try:
            detected = watcher.watcher_tick(db)
            if detected:
                print(f"[watcher] detected completion for runs: {detected}", flush=True)
        except Exception as exc:
            print(f"[watcher] error: {exc}", flush=True)
        finally:
            db.close()
        time.sleep(interval)


if __name__ == "__main__":
    main()
