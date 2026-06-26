"""Status transition rules (brief §Status Model)."""
from __future__ import annotations

TRIAGE = "Triage/Ready"
TODO = "Todo"
IN_PROGRESS = "In Progress"
BLOCKED = "Blocked"
REVIEWING = "Reviewing"
COMPLETED = "Completed"
CANCELED = "Canceled"

TERMINAL = {COMPLETED, CANCELED}

# Digest policy: what the system does when a ticket ENTERS a status block.
#   none          -> nothing automatic (plain column)
#   agent_execute -> auto-run Navigator + enqueue a run (drag = execute)
DIGEST_NONE = "none"
DIGEST_AGENT_EXECUTE = "agent_execute"

# Allowed forward edges. "Any non-terminal -> Canceled" is added below.
ALLOWED: dict[str, set[str]] = {
    # Triage/Ready -> In Progress is allowed because the plan aliases Ready=Triage:
    # "Kay sets Ready, Hermes moves it to In Progress" (validation table).
    TRIAGE: {TODO, IN_PROGRESS},
    TODO: {IN_PROGRESS},
    IN_PROGRESS: {REVIEWING, BLOCKED, COMPLETED},
    BLOCKED: {IN_PROGRESS},
    REVIEWING: {COMPLETED, IN_PROGRESS},  # Reviewing -> In Progress = Kay rerun
    COMPLETED: set(),
    CANCELED: set(),
}
for _s in list(ALLOWED):
    if _s not in TERMINAL:
        ALLOWED[_s].add(CANCELED)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED.get(from_status, set())


def allowed_targets(from_status: str) -> list[str]:
    return sorted(ALLOWED.get(from_status, set()))
