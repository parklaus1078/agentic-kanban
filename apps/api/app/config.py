"""Runtime configuration.

DB-agnostic: defaults to a local SQLite file (so the MVP runs without Docker),
but `DATABASE_URL` (set by docker-compose) overrides it to Postgres.
All paths default to the canonical locations from the brief.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SQLite by default; on the Linux fs (drvfs/9p mounts break SQLite file locks).
    database_url: str = "sqlite:////home/kay/.local/share/asv2/asv2.db"

    # Canonical external paths (brief).
    llm_wiki_root: str = "/home/kay/llm_wiki"
    wiki_raw_subdir: str = "kay_second_brain/raw/decisions/agent-system-v2"
    codex_output_dir: str = "/mnt/k/WRITTEN_BY_CODEX"
    claude_output_dir: str = "/mnt/k/WRITTEN_BY_CLAUDE"

    # Agent execution: "simulated" (deterministic, no model quota) or "real" (CLI subprocess).
    agent_mode: str = "simulated"
    codex_cmd_template: str = ""  # e.g. 'codex exec --prompt-file {prompt_file} --cd {output_dir}'
    claude_cmd_template: str = ""  # e.g. 'claude -p {prompt_file}'

    run_timeout_seconds: int = 900
    max_concurrency_per_agent: int = 1
    autoseed: bool = True
    tz_offset_hours: int = 9  # Asia/Seoul (no DST)

    model_config = SettingsConfigDict(env_prefix="ASV2_", env_file=".env", extra="ignore")


settings = Settings()

# docker-compose / 12-factor style: bare DATABASE_URL wins if present.
if os.getenv("DATABASE_URL"):
    settings.database_url = os.environ["DATABASE_URL"]


def ensure_runtime_dirs() -> None:
    """Create the local dirs we own (sqlite parent + output dirs + wiki raw dir)."""
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("sqlite:///", 1)[-1]
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    for p in (
        settings.codex_output_dir,
        settings.claude_output_dir,
        os.path.join(settings.llm_wiki_root, settings.wiki_raw_subdir),
    ):
        Path(p).mkdir(parents=True, exist_ok=True)


def output_dir_for_agent(agent: str) -> str:
    return settings.codex_output_dir if agent == "codex" else settings.claude_output_dir
