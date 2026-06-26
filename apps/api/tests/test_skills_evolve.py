"""Phase 8 — self-evolution: lesson → skill proposal (§16.1)."""


def test_propose_matches_existing_installed_skill(client):
    from app.db import SessionLocal
    from app.services import skills_evolve

    db = SessionLocal()
    # seeded skill catalog includes things like test-driven-development; a lesson about
    # writing failing tests first should match an existing skill → install_existing.
    gs = skills_evolve.propose_skill(db, "always write a failing unit test before the fix pytest")
    db.commit()
    assert gs.kind == "install_existing"
    assert gs.suggested_ref
    db.close()


def test_propose_creates_new_when_no_match(client):
    from app.db import SessionLocal
    from app.services import skills_evolve

    db = SessionLocal()
    gs = skills_evolve.propose_skill(db, "zxqw nonsense lesson with no catalog overlap qqzz")
    db.commit()
    assert gs.kind == "new" and gs.suggested_ref is None
    db.close()


def test_evolve_accept_reject_endpoints(client):
    proposed = client.post(
        "/skills/evolve", json={"lesson": "write failing pytest first then implement"}
    ).json()
    assert proposed["status"] == "proposed"

    accepted = client.post(f"/skills/generated/{proposed['id']}/accept").json()
    assert accepted["status"] == "active" and accepted["approved_by"] == "Kay"

    # a second proposal that we reject
    p2 = client.post("/skills/evolve", json={"lesson": "qqzz totally novel lesson zzxx"}).json()
    rejected = client.post(f"/skills/generated/{p2['id']}/reject").json()
    assert rejected["status"] == "retired"

    listing = client.get("/skills/generated").json()
    assert {g["id"] for g in listing} >= {proposed["id"], p2["id"]}
