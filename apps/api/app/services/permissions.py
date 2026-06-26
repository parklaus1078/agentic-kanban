"""Phase 5 — agent permission presets → official CLI flags (spec §11).

Sessions are pre-authorized at launch via official flags (no Shift+Tab). A preset
maps to the exact, documented flags per brain:

- Claude Code: ``--permission-mode <mode>`` (default|acceptEdits|plan|auto|dontAsk|
  bypassPermissions). Source: code.claude.com/docs/en/permission-modes.
- Codex: ``--sandbox <read-only|workspace-write|danger-full-access>`` ×
  ``--ask-for-approval <untrusted|on-request|never>``. Source:
  developers.openai.com/codex/agent-approvals-security.

Presets are the SSOT for "how autonomous"; the per-agent choice is stored in
``agent_permission_profiles`` and applied to settings files at launch (real mode).
"""
from __future__ import annotations

# Each preset: claude permission-mode + codex (sandbox, approval).
PRESETS: dict[str, dict] = {
    "auto": {  # default per spec §11/D9 — near-fully autonomous
        "claude_mode": "auto",
        "codex_sandbox": "workspace-write",
        "codex_approval": "on-request",
        "label": "Auto — minimal prompts",
    },
    "acceptEdits": {  # fallback when `auto` account requirements aren't met
        "claude_mode": "acceptEdits",
        "codex_sandbox": "workspace-write",
        "codex_approval": "on-request",
        "label": "Accept edits",
    },
    "safe": {  # read-only / asks before mutating
        "claude_mode": "default",
        "codex_sandbox": "read-only",
        "codex_approval": "on-request",
        "label": "Safe — read-only, ask first",
    },
    "locked": {  # only pre-approved tools, no prompts
        "claude_mode": "dontAsk",
        "codex_sandbox": "read-only",
        "codex_approval": "never",
        "label": "Locked — allowlist only",
    },
}

DEFAULT_PRESET = "auto"


def presets() -> list[dict]:
    return [{"key": k, **v} for k, v in PRESETS.items()]


def claude_flags(preset: str) -> list[str]:
    mode = PRESETS.get(preset, PRESETS[DEFAULT_PRESET])["claude_mode"]
    return ["--permission-mode", mode]


def codex_flags(preset: str) -> list[str]:
    p = PRESETS.get(preset, PRESETS[DEFAULT_PRESET])
    return ["--sandbox", p["codex_sandbox"], "--ask-for-approval", p["codex_approval"]]


def flags_for(brain: str, preset: str) -> list[str]:
    return claude_flags(preset) if brain == "claude" else codex_flags(preset)
