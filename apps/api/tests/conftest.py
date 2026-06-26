"""Test fixtures. Each test gets a fresh SQLite DB + temp wiki/output dirs so the
suite never touches the real /home/kay/llm_wiki or /mnt/k output dirs.
"""
import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="asv2-tests-")
os.environ.update(
    ASV2_DATABASE_URL=f"sqlite:///{_TMP}/test.db",
    DATABASE_URL=f"sqlite:///{_TMP}/test.db",
    ASV2_LLM_WIKI_ROOT=f"{_TMP}/llm_wiki",
    ASV2_WIKI_RAW_SUBDIR="raw/decisions/agent-system-v2",
    ASV2_CODEX_OUTPUT_DIR=f"{_TMP}/codex",
    ASV2_CLAUDE_OUTPUT_DIR=f"{_TMP}/claude",
    ASV2_AUTOSEED="0",
)

from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed.seed_all(db)
    finally:
        db.close()
    return TestClient(app)


@pytest.fixture()
def board_id(client):
    return client.get("/boards").json()[0]["id"]


def make_ticket(client, board_id, **kw):
    body = {"board_id": board_id, "title": "Test ticket", "description_md": "", "acceptance_criteria_md": ""}
    body.update(kw)
    return client.post("/tickets", json=body).json()


def move(client, ticket_id, to_status, actor="Kay"):
    return client.post(f"/tickets/{ticket_id}/transition", json={"to_status": to_status, "actor": actor})
