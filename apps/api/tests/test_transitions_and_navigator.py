from conftest import make_ticket, move


def test_valid_transition_writes_event_and_wiki(client, board_id):
    t = make_ticket(client, board_id)
    res = move(client, t["id"], "Todo")
    assert res.status_code == 200
    ev = res.json()["status_event"]
    assert ev["from_status"] == "Triage/Ready" and ev["to_status"] == "Todo"
    assert ev["wiki_raw_path"]
    import pathlib
    p = pathlib.Path(ev["wiki_raw_path"])
    assert p.exists()
    text = p.read_text()
    assert "type: agent_ticket_event" in text
    assert "status_to: Todo" in text


def test_started_at_set_on_in_progress(client, board_id):
    t = make_ticket(client, board_id)
    move(client, t["id"], "Todo")
    move(client, t["id"], "In Progress", actor="Hermes")
    td = client.get(f"/tickets/{t['id']}").json()
    assert td["status"] == "In Progress"
    assert td["started_at"] is not None


def test_illegal_transition_rejected(client, board_id):
    t = make_ticket(client, board_id)
    # Triage/Ready -> Reviewing is not allowed
    assert move(client, t["id"], "Reviewing").status_code == 409
    move(client, t["id"], "Todo")
    # Todo -> Completed not allowed
    assert move(client, t["id"], "Completed").status_code == 409


def test_any_nonterminal_to_canceled(client, board_id):
    t = make_ticket(client, board_id)
    move(client, t["id"], "Todo")
    res = move(client, t["id"], "Canceled")
    assert res.status_code == 200
    td = client.get(f"/tickets/{t['id']}").json()
    assert td["status"] == "Canceled" and td["canceled_at"] is not None


def test_comments_create_and_list(client, board_id):
    t = make_ticket(client, board_id)
    client.post(f"/tickets/{t['id']}/comments",
                json={"author_type": "kay", "author_name": "Kay", "body_md": "Looks good $E=mc^2$"})
    comments = client.get(f"/tickets/{t['id']}/comments").json()
    assert len(comments) == 1
    assert "$E=mc^2$" in comments[0]["body_md"]  # LaTeX preserved raw


def test_navigator_classifies_engineering(client, board_id):
    t = make_ticket(client, board_id, title="Set up Kubernetes deploy pipeline",
                    description_md="Need docker and k8s ci/cd pipeline with terraform")
    nav = client.post(f"/tickets/{t['id']}/navigator/recommend", json={}).json()
    assert nav["persona"] == "DevOps"
    assert nav["agent"] == "claude"
    assert nav["confidence"] > 0.5
    assert nav["alternatives"]


def test_navigator_classifies_business(client, board_id):
    t = make_ticket(client, board_id, title="Plan marketing campaign",
                    description_md="Design a marketing campaign with seo and brand positioning and ads")
    nav = client.post(f"/tickets/{t['id']}/navigator/recommend", json={}).json()
    assert nav["persona"] == "Marketer"
    assert nav["agent"] == "codex"


def test_navigator_manual_override(client, board_id):
    t = make_ticket(client, board_id, title="ambiguous task")
    nav = client.post(f"/tickets/{t['id']}/navigator/recommend",
                      json={"override": {"persona": "SecOps", "agent": "claude"}}).json()
    assert nav["persona"] == "SecOps"
    assert nav["manual_override"] is True
