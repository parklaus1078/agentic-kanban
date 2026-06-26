"""Phase 6 — recursive subdivision + parent auto-complete (§8)."""
from conftest import make_ticket, move


def _complete_child(client, child_id):
    move(client, child_id, "In Progress")  # auto-enqueues a run
    client.post("/admin/worker/tick")
    client.post("/admin/watcher/tick")
    client.post(f"/tickets/{child_id}/review", json={"satisfied": True})


def test_subdivide_proposes_children(client, board_id):
    t = make_ticket(client, board_id, title="Build a Todo app", description_md="a full app")
    prop = client.post(f"/tickets/{t['id']}/subdivide").json()
    assert prop["status"] == "proposed"
    titles = [c["title"] for c in prop["proposed_children_json"]]
    assert any("Backend" in x for x in titles)  # project-sized → BE/FE/DB/...
    assert client.get(f"/tickets/{t['id']}/subdivision").json()["id"] == prop["id"]


def test_approve_creates_children_recursively(client, board_id):
    t = make_ticket(client, board_id, title="Build a platform")
    prop = client.post(f"/tickets/{t['id']}/subdivide").json()
    children = client.post(f"/subdivisions/{prop['id']}/approve").json()
    assert len(children) == len(prop["proposed_children_json"])
    for c in children:
        assert c["parent_ticket_id"] == t["id"] and c["status"] == "Todo"
    # recursive: a child can itself be subdivided
    p2 = client.post(f"/tickets/{children[0]['id']}/subdivide").json()
    assert p2["parent_ticket_id"] == children[0]["id"]


def test_reject_proposal(client, board_id):
    t = make_ticket(client, board_id, title="small task")
    prop = client.post(f"/tickets/{t['id']}/subdivide").json()
    r = client.post(f"/subdivisions/{prop['id']}/reject").json()
    assert r["status"] == "rejected"


def test_parent_autocompletes_when_all_children_done(client, board_id):
    parent = make_ticket(client, board_id, title="Build a service")
    prop = client.post(f"/tickets/{parent['id']}/subdivide").json()
    children = client.post(f"/subdivisions/{prop['id']}/approve").json()
    for c in children:
        _complete_child(client, c["id"])
    assert client.get(f"/tickets/{parent['id']}").json()["status"] == "Completed"


def test_autocomplete_toggle_off_keeps_parent_open(client, board_id):
    parent = make_ticket(client, board_id, title="Build a website")
    client.patch(f"/tickets/{parent['id']}", json={"auto_complete_parent": False})
    prop = client.post(f"/tickets/{parent['id']}/subdivide").json()
    children = client.post(f"/subdivisions/{prop['id']}/approve").json()
    for c in children:
        _complete_child(client, c["id"])
    # parent stays open because the toggle is off
    assert client.get(f"/tickets/{parent['id']}").json()["status"] != "Completed"
