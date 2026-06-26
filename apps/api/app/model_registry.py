"""Phase 5 — model registry (Single Source of Truth, spec §12).

Every place that needs a model (Navigator decisions, per-persona defaults, ticket
overrides, the UI picker) reads from HERE — no model id is hand-typed elsewhere.
IDs are the official ones (Claude Code model-config; OpenAI Codex models docs).
``default: True`` marks the latest/recommended model per brain. Update this one
file when the official lists change.
"""
from __future__ import annotations

MODELS: dict[str, list[dict]] = {
    "claude": [
        {"id": "claude-opus-4-8", "display": "Opus 4.8", "latest": True, "default": True, "effort": []},
        {"id": "claude-sonnet-4-6", "display": "Sonnet 4.6", "latest": False, "default": False, "effort": []},
        {"id": "claude-haiku-4-5", "display": "Haiku 4.5", "latest": False, "default": False, "effort": []},
        {"id": "claude-fable-5", "display": "Fable 5", "latest": False, "default": False, "effort": []},
    ],
    "codex": [
        {"id": "gpt-5.5", "display": "GPT-5.5", "latest": True, "default": True,
         "effort": ["minimal", "low", "medium", "high", "xhigh"]},
        {"id": "gpt-5.4", "display": "GPT-5.4", "latest": False, "default": False,
         "effort": ["minimal", "low", "medium", "high", "xhigh"]},
        {"id": "gpt-5.4-mini", "display": "GPT-5.4 mini", "latest": False, "default": False,
         "effort": ["minimal", "low", "medium", "high", "xhigh"]},
    ],
}


def list_models(brain: str) -> list[dict]:
    return MODELS.get(brain, [])


def default_model(brain: str) -> str | None:
    for m in MODELS.get(brain, []):
        if m.get("default"):
            return m["id"]
    return None


def is_known(brain: str, model_id: str) -> bool:
    return any(m["id"] == model_id for m in MODELS.get(brain, []))
