import pathlib

from conftest import make_ticket, move


def _auto_run(client, ticket_id):
    """The run auto-enqueued when the ticket entered an `agent_execute` status."""
    return client.get(f"/tickets/{ticket_id}").json()["runs"][-1]


def _to_in_progress(client, board_id, **kw):
    t = make_ticket(client, board_id, **kw)
    move(client, t["id"], "Todo")
    move(client, t["id"], "In Progress")  # entering In Progress auto-enqueues a run
    return t


def test_drag_to_in_progress_auto_enqueues_run(client, board_id):
    # Entering an `agent_execute` status (In Progress) is the trigger: it must
    # auto-create a queued run + queue item, with no explicit POST /runs.
    t = make_ticket(client, board_id, title="auto dispatch",
                    description_md="build a fastapi endpoint and react component")
    move(client, t["id"], "Todo")
    assert client.get(f"/tickets/{t['id']}").json()["runs"] == []  # nothing queued yet

    move(client, t["id"], "In Progress")

    td = client.get(f"/tickets/{t['id']}").json()
    assert len(td["runs"]) == 1
    run = td["runs"][0]
    assert run["status"] == "queued" and run["output_path"]
    assert td["navigator_decision"] is not None
    q = client.get("/queue").json()
    assert sum(1 for qi in q if qi["ticket_id"] == t["id"]) == 1


def test_non_digestible_status_does_not_dispatch(client, board_id):
    t = make_ticket(client, board_id)
    move(client, t["id"], "Todo")  # Todo is not agent_execute
    assert client.get(f"/tickets/{t['id']}").json()["runs"] == []


def test_no_double_dispatch_on_reenter(client, board_id):
    # Re-entering In Progress while a run is still active must not duplicate.
    t = make_ticket(client, board_id)
    move(client, t["id"], "Todo")
    move(client, t["id"], "In Progress")
    move(client, t["id"], "Blocked")
    move(client, t["id"], "In Progress")
    assert len(client.get(f"/tickets/{t['id']}").json()["runs"]) == 1


def test_full_lifecycle_to_completed(client, board_id):
    t = _to_in_progress(client, board_id, title="Implement FastAPI endpoint",
                        description_md="build a react component and fastapi endpoint")
    run = _auto_run(client, t["id"])
    assert run["status"] == "queued" and run["output_path"]

    assert client.post("/admin/worker/tick").json()["processed"] == [run["id"]]
    # after worker tick the run is running and the artifact + sentinel exist on disk
    out = pathlib.Path(run["output_path"])
    assert (out / "result.md").exists()
    assert (out / ".agent_done.json").exists()

    assert client.post("/admin/watcher/tick").json()["detected"] == [run["id"]]

    td = client.get(f"/tickets/{t['id']}").json()
    assert td["status"] == "Reviewing"

    rd = client.get(f"/runs/{run['id']}").json()
    assert rd["status"] == "success"
    assert len(rd["artifacts"]) == 1
    assert rd["artifacts"][0]["checksum"]
    event_types = [w["event_type"] for w in rd["watcher_events"]]
    assert "sentinel_detected" in event_types and "completed" in event_types

    rev = client.post(f"/tickets/{t['id']}/review", json={"satisfied": True}).json()
    assert rev["ticket"]["status"] == "Completed"
    assert rev["ticket"]["completed_at"] is not None
    assert rev["rerun"] is None


def test_review_rerun_includes_comment(client, board_id):
    t = _to_in_progress(client, board_id)
    run = _auto_run(client, t["id"])
    client.post("/admin/worker/tick")
    client.post("/admin/watcher/tick")
    assert client.get(f"/tickets/{t['id']}").json()["status"] == "Reviewing"

    rev = client.post(f"/tickets/{t['id']}/review",
                      json={"satisfied": False, "comment_md": "Please add input validation"}).json()
    assert rev["ticket"]["status"] == "In Progress"
    assert rev["rerun"]["run_number"] == 2
    assert "Please add input validation" in rev["rerun"]["prompt_md"]
    assert "RERUN" in rev["rerun"]["prompt_md"]

    # the rerun can be driven to completion too
    client.post("/admin/worker/tick")
    client.post("/admin/watcher/tick")
    assert client.get(f"/tickets/{t['id']}").json()["status"] == "Reviewing"


def test_failed_run_blocks_ticket(client, board_id):
    t = _to_in_progress(client, board_id)
    run = _auto_run(client, t["id"])
    client.post("/admin/worker/tick")
    # corrupt the sentinel to report failure
    out = pathlib.Path(run["output_path"])
    (out / ".agent_done.json").write_text('{"status":"failed","error":"boom","artifacts":[]}')
    client.post("/admin/watcher/tick")
    td = client.get(f"/tickets/{t['id']}").json()
    assert td["status"] == "Blocked"
    assert client.get(f"/runs/{run['id']}").json()["status"] == "failed"


def test_watcher_timeout_blocks_ticket(client, board_id):
    from app.config import settings

    t = _to_in_progress(client, board_id)
    run = _auto_run(client, t["id"])
    client.post("/admin/worker/tick")
    # remove the sentinel so the run never "completes"
    (pathlib.Path(run["output_path"]) / ".agent_done.json").unlink()
    old = settings.run_timeout_seconds
    settings.run_timeout_seconds = 0
    try:
        client.post("/admin/watcher/tick")
    finally:
        settings.run_timeout_seconds = old
    assert client.get(f"/tickets/{t['id']}").json()["status"] == "Blocked"
    rd = client.get(f"/runs/{run['id']}").json()
    assert rd["status"] == "failed"
    assert any(w["event_type"] == "timeout" for w in rd["watcher_events"])


def test_watcher_detects_process_exit(client, board_id):
    from app.db import SessionLocal
    from app.models import AgentRun

    t = _to_in_progress(client, board_id)
    run = _auto_run(client, t["id"])
    client.post("/admin/worker/tick")
    (pathlib.Path(run["output_path"]) / ".agent_done.json").unlink()
    # simulate a real CLI process that exited without writing a sentinel
    db = SessionLocal()
    r = db.get(AgentRun, run["id"])
    r.process_id = "2147483646"  # a pid that does not exist
    db.commit()
    db.close()
    client.post("/admin/watcher/tick")
    assert client.get(f"/tickets/{t['id']}").json()["status"] == "Blocked"
    rd = client.get(f"/runs/{run['id']}").json()
    assert rd["status"] == "failed"
    assert any(w["event_type"] == "process_exit" for w in rd["watcher_events"])


def test_queue_reorder_and_cancel(client, board_id):
    # two queued claude runs (concurrency 1 => both stay queued until a worker tick)
    runs = []
    for i in range(2):
        t = _to_in_progress(client, board_id, title=f"task {i}")
        runs.append(_auto_run(client, t["id"]))

    q = client.get("/queue").json()
    assert [qi["state"] for qi in q] == ["queued", "queued"]
    ids = [qi["id"] for qi in q]

    # reverse order
    reordered = client.patch("/queue/reorder", json={"ordered_ids": list(reversed(ids))}).json()
    assert [qi["id"] for qi in reordered] == list(reversed(ids))

    # cancel the first queue item
    cancelled = client.post(f"/queue/{ids[0]}/cancel").json()
    assert cancelled["state"] == "canceled"
    # its run is canceled too
    run_id = next(qi["run_id"] for qi in q if qi["id"] == ids[0])
    assert client.get(f"/runs/{run_id}").json()["status"] == "canceled"


def test_run_cancel_endpoint(client, board_id):
    t = _to_in_progress(client, board_id)
    run = _auto_run(client, t["id"])
    res = client.post(f"/runs/{run['id']}/cancel").json()
    assert res["status"] == "canceled"
    td = client.get(f"/tickets/{t['id']}").json()
    assert td["status"] == "Canceled"
    assert td["canceled_at"] is not None
    events = td["status_events"]
    assert events[-1]["from_status"] == "In Progress"
    assert events[-1]["to_status"] == "Canceled"
    assert events[-1]["actor"] == "Kay"
    # cancelling again -> 409
    assert client.post(f"/runs/{run['id']}/cancel").status_code == 409


def test_wiki_sync_jobs_and_fork(client, board_id):
    t = make_ticket(client, board_id)
    move(client, t["id"], "Todo")  # creates a wiki sync job
    jobs = client.get("/wiki-sync/jobs").json()
    assert len(jobs) >= 1
    forked = client.post(f"/wiki-sync/tickets/{t['id']}/fork-raw", json={"note_md": "manual note"}).json()
    assert pathlib.Path(forked["raw_path"]).exists()
