"""Thin launcher: run the worker loop without Docker.

Usage (from repo root):  python services/worker/run.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.worker_loop import main  # noqa: E402

if __name__ == "__main__":
    main()
