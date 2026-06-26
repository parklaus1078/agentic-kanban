"""Phase 5 — interactive CLI execution in a dedicated tmux session (spec §10).

Pure command builders for opening a NEW WINDOW in the dedicated tmux session and
running an INTERACTIVE Codex/Claude CLI (not print/exec — Kay's subscription plans
perform better interactively), pre-authorized via official permission flags (§11)
with the chosen model (§12), piping the pane to a run log for the live view (§13).

The builders are pure and unit-tested. The host daemon runs them in ``agent_mode``
``real``; actual interactive verification needs a logged-in CLI session, so the
spawn itself is guarded elsewhere.
"""
from __future__ import annotations

import shlex

from . import permissions

TMUX_SESSION = "asv2"


def window_name(run_id: int) -> str:
    return f"run-{run_id}"


def cli_invocation(brain: str, model_id: str, preset: str) -> list[str]:
    """The interactive CLI argv: base + model + pre-authorized permission flags."""
    base = "claude" if brain == "claude" else "codex"
    return [base, "--model", model_id, *permissions.flags_for(brain, preset)]


def build_new_window_command(run_id: int, brain: str, model_id: str, preset: str, log_path: str) -> list[str]:
    """`tmux new-window` (detached) in the dedicated session, piping the pane to the
    run log so the board's live view can tail it."""
    cli = " ".join(shlex.quote(a) for a in cli_invocation(brain, model_id, preset))
    shell = f"{cli} 2>&1 | tee {shlex.quote(log_path)}"
    return ["tmux", "new-window", "-d", "-t", TMUX_SESSION, "-n", window_name(run_id), shell]


def send_prompt_command(run_id: int, prompt_file: str) -> list[str]:
    """Type the built prompt into the interactive session (reads the file content)."""
    win = f"{TMUX_SESSION}:{window_name(run_id)}"
    return ["tmux", "send-keys", "-t", win, f"$(cat {shlex.quote(prompt_file)})", "Enter"]


def capture_pane_command(run_id: int) -> list[str]:
    """Snapshot the pane (Watcher reads this to detect start/progress/permission/done)."""
    win = f"{TMUX_SESSION}:{window_name(run_id)}"
    return ["tmux", "capture-pane", "-p", "-t", win]


def kill_window_command(run_id: int) -> list[str]:
    win = f"{TMUX_SESSION}:{window_name(run_id)}"
    return ["tmux", "kill-window", "-t", win]
