"""Phase 3 — data durability / fail-safe."""
from conftest import make_ticket, move


def test_recover_requeues_interrupted_runs(client, board_id):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AgentRun, QueueItem
    from app.services import durability

    t = make_ticket(client, board_id, title="recover me")
    move(client, t["id"], "Todo")
    move(client, t["id"], "In Progress")  # auto-enqueues a queued run

    db = SessionLocal()
    run = db.scalars(select(AgentRun).where(AgentRun.ticket_id == t["id"])).first()
    qi = db.scalars(select(QueueItem).where(QueueItem.run_id == run.id)).first()
    # simulate a power-cut mid-flight: run + queue item stuck "running"
    run.status, run.process_id = "running", "sim-123"
    qi.state, qi.locked_by = "running", "worker"
    db.commit()

    n = durability.recover_interrupted_runs(db)
    assert n == 1
    db.refresh(run)
    db.refresh(qi)
    assert run.status == "queued" and run.process_id is None
    assert qi.state == "queued" and qi.locked_by is None
    db.close()


def test_create_snapshot_is_noop_on_sqlite(tmp_path):
    from app.services import durability

    # The fail-safe targets the container Postgres; on the SQLite test DB it skips.
    assert durability.create_snapshot("20260626-000000", out_dir=str(tmp_path)) is None


def test_prune_keeps_newest(tmp_path):
    from app.services import durability

    for name in ("asv2-1.sql", "asv2-2.sql", "asv2-3.sql"):
        (tmp_path / name).write_text("x")
    removed = durability.prune_snapshots(keep=2, out_dir=str(tmp_path))
    remaining = durability.list_snapshots(str(tmp_path))
    assert len(remaining) == 2
    assert any(r.endswith("asv2-1.sql") for r in removed)


def test_list_snapshots_missing_dir(tmp_path):
    from app.services import durability

    assert durability.list_snapshots(str(tmp_path / "nope")) == []


def test_system_and_scheduled_jobs_endpoints(client):
    assert isinstance(client.get("/system/snapshots").json(), list)
    assert client.get("/scheduled-jobs").json() == []
