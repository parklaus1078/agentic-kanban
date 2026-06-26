"""Phase 2 — Project CRUD (above boards) + board templates."""


def test_board_templates_listed(client):
    tpls = client.get("/board-templates").json()
    assert any(t["name"] == "Standard Kanban" for t in tpls)


def test_create_project_creates_seeded_board(client):
    tpl = client.get("/board-templates").json()[0]
    p = client.post("/projects", json={"title": "My Todo App", "board_template_id": tpl["id"]}).json()
    assert p["slug"] == "my-todo-app"
    assert p["status"] == "active"
    assert p["board_id"]
    # the created board is seeded with statuses, In Progress carrying the agent_execute policy
    blocks = client.get(f"/boards/{p['board_id']}/status-blocks").json()
    policy = {b["name"]: b["digest_policy"] for b in blocks}
    assert policy.get("In Progress") == "agent_execute"


def test_list_get_update_archive_project(client):
    p = client.post("/projects", json={"title": "Proj X"}).json()
    assert any(x["id"] == p["id"] for x in client.get("/projects").json())

    got = client.get(f"/projects/{p['id']}").json()
    assert got["title"] == "Proj X"

    upd = client.patch(f"/projects/{p['id']}", json={"title": "Proj X2", "description": "d"}).json()
    assert upd["title"] == "Proj X2" and upd["description"] == "d"

    arch = client.post(f"/projects/{p['id']}/archive").json()
    assert arch["status"] == "archived"


def test_slug_is_unique(client):
    a = client.post("/projects", json={"title": "Same Name"}).json()
    b = client.post("/projects", json={"title": "Same Name"}).json()
    assert a["slug"] == "same-name"
    assert b["slug"] != a["slug"] and b["slug"].startswith("same-name")
