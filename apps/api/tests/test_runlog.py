"""Phase 5/§13 — run log polling endpoint."""
from conftest import make_ticket, move


def test_run_log_polling(client, board_id):
    t = make_ticket(client, board_id, title="log me", description_md="build a fastapi endpoint")
    move(client, t["id"], "Todo")
    move(client, t["id"], "In Progress")  # auto-enqueues a run
    client.post("/admin/worker/tick")  # executes (simulated) → writes run.log

    run = client.get(f"/tickets/{t['id']}").json()["runs"][-1]
    log = client.get(f"/runs/{run['id']}/log").json()
    assert "session" in log["content"]
    assert log["offset"] > 0
