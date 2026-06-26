from conftest import make_ticket


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_seed_and_default_board(client):
    board = client.get("/boards").json()[0]
    names = [s["name"] for s in board["status_blocks"]]
    assert names == ["Triage/Ready", "Todo", "In Progress", "Blocked", "Reviewing", "Completed", "Canceled"]
    # In Progress is the digestible status by default
    digest = {s["name"]: s["is_agent_digestible"] for s in board["status_blocks"]}
    assert digest["In Progress"] is True
    terminal = {s["name"]: s["is_terminal"] for s in board["status_blocks"]}
    assert terminal["Completed"] and terminal["Canceled"]


def test_personas_catalog(client):
    personas = client.get("/personas").json()
    names = {p["persona_name"] for p in personas}
    assert len(personas) == 17
    # Codex (business) group
    for n in ["PM", "QA(E2E)", "Marketer", "Accountant", "Strategist", "CS Manager", "Researcher"]:
        assert n in names
    # Claude (engineering) group
    for n in ["CTO", "Full Stack Developer", "DevOps", "Android Engineer", "iOS Engineer",
              "AI Engineer", "MLOps", "Data Engineer", "QA(Unit test)", "SecOps"]:
        assert n in names
    by_name = {p["persona_name"]: p for p in personas}
    assert by_name["PM"]["default_agent"] == "codex"
    assert by_name["Full Stack Developer"]["default_agent"] == "claude"


def test_skills_catalog(client):
    skills = client.get("/skills").json()
    assert len(skills) >= 12
    tdd = next(s for s in skills if s["name"] == "test-driven-development")
    assert "testing" in tdd["tags"]


def test_status_block_add_toggle_delete(client, board_id):
    block = client.post(f"/boards/{board_id}/status-blocks",
                        json={"name": "Spike", "is_agent_digestible": False}).json()
    assert block["name"] == "Spike"
    patched = client.patch(f"/status-blocks/{block['id']}", json={"is_agent_digestible": True}).json()
    assert patched["is_agent_digestible"] is True
    assert client.delete(f"/status-blocks/{block['id']}").status_code == 204


def test_cannot_delete_status_block_with_tickets(client, board_id):
    make_ticket(client, board_id)  # lands in Triage/Ready
    blocks = client.get(f"/boards/{board_id}/status-blocks").json()
    triage = next(b for b in blocks if b["name"] == "Triage/Ready")
    assert client.delete(f"/status-blocks/{triage['id']}").status_code == 409


def test_ticket_number_autoincrement(client, board_id):
    t1 = make_ticket(client, board_id, title="one")
    t2 = make_ticket(client, board_id, title="two")
    assert t1["ticket_number"] == "ASV2-0001"
    assert t2["ticket_number"] == "ASV2-0002"
    assert t1["status"] == "Triage/Ready"
