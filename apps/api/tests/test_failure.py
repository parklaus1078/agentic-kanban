"""Phase 4a — failure & rate-limit classification + scheduling."""
from datetime import datetime, timedelta

from conftest import make_ticket, move


def test_classify_claude_session_limit():
    from app.services import failure

    c = failure.classify("...\nYou've hit your session limit · resets 3:45pm\n")
    assert c.cls == failure.FailureClass.USAGE_LIMIT
    assert c.reset_hint == "3:45pm"


def test_classify_claude_weekly_limit_day_form():
    from app.services import failure

    c = failure.classify("You've hit your weekly limit · resets Mon 12:00am")
    assert c.cls == failure.FailureClass.USAGE_LIMIT
    assert "Mon 12:00am" in (c.reset_hint or "")


def test_classify_codex_usage_limit_with_try_again():
    from app.services import failure

    c = failure.classify("You've hit your usage limit. Try again at 3:05 PM.")
    assert c.cls == failure.FailureClass.USAGE_LIMIT
    assert c.reset_hint == "3:05 PM"


def test_429_is_transient_not_usage_limit():
    from app.services import failure

    c = failure.classify("API Error: Request rejected (429) · temporary capacity")
    assert c.cls == failure.FailureClass.TRANSIENT


def test_server_throttle_is_transient_not_usage_limit():
    from app.services import failure

    # This string contains "usage limit" but explicitly is NOT one — must not misclassify.
    c = failure.classify(
        "API Error: Server is temporarily limiting requests (not your usage limit)"
    )
    assert c.cls == failure.FailureClass.TRANSIENT


def test_clean_output_is_none():
    from app.services import failure

    assert failure.classify("Writing auth_router.py ... done").cls == failure.FailureClass.NONE


def test_fallback_brain():
    from app.services import failure

    assert failure.fallback_brain("claude") == "codex"
    assert failure.fallback_brain("codex") == "claude"
    assert failure.fallback_brain("other") is None


def test_schedule_rate_limit_resume_creates_job(client, board_id):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AgentRun, ScheduledJob
    from app.services import failure

    t = make_ticket(client, board_id, title="rate me")
    move(client, t["id"], "Todo")
    move(client, t["id"], "In Progress")
    db = SessionLocal()
    run = db.scalars(select(AgentRun).where(AgentRun.ticket_id == t["id"])).first()
    fire_at = datetime.utcnow() + timedelta(hours=5)
    job = failure.schedule_rate_limit_resume(db, run, fire_at, snapshot_path="/tmp/x.log")
    db.commit()
    db.refresh(run)
    assert run.status == "rate_limited"
    assert job.kind == "ratelimit_resume" and job.run_id == run.id
    assert job.payload_json.get("snapshot") == "/tmp/x.log"
    found = db.scalars(select(ScheduledJob).where(ScheduledJob.run_id == run.id)).first()
    assert found is not None and found.status == "pending"
    db.close()
