"""Thin launcher: run the watcher loop without Docker.

Usage (from repo root):  python services/watcher/run.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.watcher_loop import main  # noqa: E402

if __name__ == "__main__":
    main()
