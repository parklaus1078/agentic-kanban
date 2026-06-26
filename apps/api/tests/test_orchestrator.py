"""Phase 4b — LangGraph StateGraph orchestration (simulated execution)."""
from conftest import make_ticket, move


def test_route_after_dispatch():
    from app.services import failure, orchestrator

    assert orchestrator.route_after_dispatch({"failure_cls": failure.FailureClass.NONE}) == "watch"
    assert (
        orchestrator.route_after_dispatch({"failure_cls": failure.FailureClass.USAGE_LIMIT})
        == "rate_limited"
    )
    assert (
        orchestrator.route_after_dispatch(
            {"failure_cls": failure.FailureClass.TRANSIENT, "retries": 0}
        )
        == "retry"
    )
    assert (
        orchestrator.route_after_dispatch(
            {"failure_cls": failure.FailureClass.TRANSIENT, "retries": 3}
        )
        == "blocked"
    )


def test_graph_drives_ticket_to_reviewing(client, board_id):
    from app.services import orchestrator

    t = make_ticket(
        client, board_id, title="orchestrate me",
        description_md="build a fastapi endpoint with tests",
    )
    move(client, t["id"], "Todo")  # stays out of In Progress so no auto-run yet

    orchestrator.run_ticket(t["id"])  # navigate → dispatch → watch

    td = client.get(f"/tickets/{t['id']}").json()
    assert td["status"] == "Reviewing"
    assert td["runs"] and td["runs"][-1]["status"] == "success"
