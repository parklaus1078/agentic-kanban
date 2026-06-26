"""Phase 4 — failure & rate-limit policy (spec §5.1, §14).

Classifies captured CLI output into a failure class so the orchestrator can decide
the next action:

- ``transient`` (raw-API 429, capacity throttle, dropped stream) → retry with
  backoff, then fall back to the other brain, then Blocked.
- ``usage_limit`` (plan/subscription allowance exhausted) → snapshot the log,
  schedule a resume at the reset time, surface it on the ticket, resume later.
- ``none`` → no failure detected.

The detection strings are the SINGLE SOURCE OF TRUTH and come from official
sources: Claude Code ``errors.md`` and the ``openai/codex`` source
(``protocol/src/error.rs``). They live in lists so they can be extended without
touching call sites; the precise reset *time* is parsed downstream (a Haiku call
in real mode), this module only extracts the human hint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import AgentRun, ScheduledJob


class FailureClass:
    USAGE_LIMIT = "usage_limit"
    TRANSIENT = "transient"
    NONE = "none"


# Plan/subscription usage limits — schedule a resume at reset (§14).
USAGE_LIMIT_PATTERNS = [
    r"You've hit your (?:session|weekly|Opus) limit",  # Claude Code (errors.md)
    r"You've hit your usage limit",  # Codex (protocol/src/error.rs)
    r"Usage limit reached\.",  # Codex TUI workspace variant
]

# Transient — capacity/throttle/raw-API rate. Retry; NOT a plan limit. Order
# matters: these are checked only after the usage-limit patterns miss, and the
# Claude throttle line deliberately disclaims "(not your usage limit)".
TRANSIENT_PATTERNS = [
    r"Request rejected \(429\)",  # Claude Code 429
    r"Server is temporarily limiting requests",  # Claude Code capacity throttle
    r"Rate limit reached for ",  # Codex raw-API 429 (per-minute TPM)
]

# Reset hints: Claude "resets 3:45pm" / "resets Mon 12:00am"; Codex "Try again at 3:05 PM."
_CLAUDE_RESET_RE = re.compile(r"resets ([^.\n]+?)(?:[.\n]|$)")
_CODEX_RESET_RE = re.compile(r"Try again at ([^.\n]+)")

FALLBACK_BRAIN = {"claude": "codex", "codex": "claude"}


@dataclass
class Classification:
    cls: str
    reset_hint: str | None = None  # human reset string; parsed precisely downstream


def classify(output: str) -> Classification:
    text = output or ""
    if any(re.search(p, text) for p in USAGE_LIMIT_PATTERNS):
        m = _CLAUDE_RESET_RE.search(text) or _CODEX_RESET_RE.search(text)
        return Classification(FailureClass.USAGE_LIMIT, m.group(1).strip() if m else None)
    if any(re.search(p, text) for p in TRANSIENT_PATTERNS):
        return Classification(FailureClass.TRANSIENT)
    return Classification(FailureClass.NONE)


def fallback_brain(agent: str) -> str | None:
    return FALLBACK_BRAIN.get(agent)


def schedule_rate_limit_resume(
    db: Session,
    run: AgentRun,
    fire_at: datetime,
    snapshot_path: str | None = None,
) -> ScheduledJob:
    """Mark the run rate-limited and enqueue a durable resume job for ``fire_at``.
    The job is re-armed on boot (Phase 3), so it survives a power cut."""
    run.status = "rate_limited"
    job = ScheduledJob(
        kind="ratelimit_resume",
        run_id=run.id,
        fire_at=fire_at,
        payload_json={"snapshot": snapshot_path},
        status="pending",
    )
    db.add(job)
    db.flush()
    return job
