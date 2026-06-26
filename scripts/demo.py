"""End-to-end demo of the Agent System v2 lifecycle.

Runs in-process (FastAPI TestClient — no server needed) against the CANONICAL
paths, so it writes REAL artifacts under /mnt/k/WRITTEN_BY_* and a REAL wiki raw
event under /home/kay/llm_wiki/.../raw/decisions/agent-system-v2/.

Proves: create -> Todo -> In Progress -> Navigator -> run -> worker -> watcher
-> Reviewing -> review NO (rerun w/ comment) -> rerun -> review YES -> Completed.

Usage:  python scripts/demo.py
A dedicated demo SQLite DB is used so reruns start clean.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

# Dedicated demo DB (clean each run); real wiki + output dirs (canonical).
DEMO_DB = Path.home() / ".local/share/asv2/demo.db"
DEMO_DB.parent.mkdir(parents=True, exist_ok=True)
if DEMO_DB.exists():
    DEMO_DB.unlink()
os.environ.setdefault("ASV2_DATABASE_URL", f"sqlite:///{DEMO_DB}")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DEMO_DB}")
os.environ.setdefault("ASV2_AUTOSEED", "1")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

STEP = 0


def step(msg: str) -> None:
    global STEP
    STEP += 1
    print(f"\n=== STEP {STEP}: {msg} ===")


def main() -> None:
    with TestClient(app) as c:
        step("Seed default board + personas + skills")
        seed = c.post("/admin/seed").json()
        board_id = seed["board"]["id"]
        statuses = [s["name"] for s in seed["board"]["status_blocks"]]
        print(f"board {board_id}; statuses: {statuses}")
        print(f"personas: {len(c.get('/personas').json())}, skills: {len(c.get('/skills').json())}")

        step("Create a ticket (lands in Triage/Ready)")
        t = c.post("/tickets", json={
            "board_id": board_id,
            "title": "Build a FastAPI + React CRUD feature with tests",
            "description_md": "Implement a REST endpoint and a React component. Include pytest and typescript build.",
            "acceptance_criteria_md": "- pytest passes\n- `npm run build` succeeds\n- endpoint returns 201 on create",
        }).json()
        tid = t["id"]
        print(f"{t['ticket_number']} created, status={t['status']}")

        step("Move Triage/Ready -> Todo -> In Progress")
        c.post(f"/tickets/{tid}/transition", json={"to_status": "Todo", "actor": "Kay"})
        ev = c.post(f"/tickets/{tid}/transition", json={"to_status": "In Progress", "actor": "Hermes"}).json()
        print(f"status={ev['ticket']['status']}; wiki_raw_path={ev['status_event']['wiki_raw_path']}")

        step("Navigator recommends persona / agent / model / skills")
        nav = c.post(f"/tickets/{tid}/navigator/recommend", json={}).json()
        print(f"persona={nav['persona']} agent={nav['agent']} model={nav['model']} "
              f"confidence={nav['confidence']}")
        print(f"skills={nav['skills']}")
        print(f"reason={nav['reason']}")
        print(f"alternatives={nav['alternatives']}")

        step("Create an agent run from the ticket")
        run = c.post(f"/tickets/{tid}/runs", json={"use_navigator": True}).json()
        print(f"run id={run['id']} status={run['status']} agent={run['agent']} output_path={run['output_path']}")

        step("Worker tick: adapter executes -> writes artifact + .agent_done.json sentinel")
        print("processed runs:", c.post("/admin/worker/tick").json()["processed"])
        out = Path(run["output_path"])
        print("files on disk:", sorted(p.name for p in out.iterdir()))

        step("Watcher tick: detects sentinel -> Reviewing")
        print("detected runs:", c.post("/admin/watcher/tick").json()["detected"])
        rd = c.get(f"/runs/{run['id']}").json()
        print(f"run status={rd['status']}; artifacts={[a['path'] for a in rd['artifacts']]}")
        print(f"watcher_events={[w['event_type'] for w in rd['watcher_events']]}")
        print("ticket status:", c.get(f"/tickets/{tid}").json()["status"])

        step("Kay review: NOT satisfied -> rerun with comment fed into next prompt")
        rev = c.post(f"/tickets/{tid}/review",
                     json={"satisfied": False, "comment_md": "Add input validation and a 400 path."}).json()
        rerun = rev["rerun"]
        print(f"ticket back to {rev['ticket']['status']}; rerun run #{rerun['run_number']}")
        has = "Add input validation" in rerun["prompt_md"]
        print(f"rerun prompt contains the review comment: {has}")

        step("Drive the rerun to completion, then approve")
        c.post("/admin/worker/tick")
        c.post("/admin/watcher/tick")
        print("ticket status after rerun:", c.get(f"/tickets/{tid}").json()["status"])
        done = c.post(f"/tickets/{tid}/review", json={"satisfied": True}).json()
        print(f"ticket status={done['ticket']['status']} completed_at={done['ticket']['completed_at']}")

        step("Queue snapshot")
        for qi in c.get("/queue").json():
            print(f"  queue#{qi['order_index']} item={qi['id']} run={qi['run_id']} state={qi['state']}")

        step("Verify the LLM Wiki raw event file on disk")
        events = c.get(f"/tickets/{tid}").json()["status_events"]
        raw = next(e["wiki_raw_path"] for e in reversed(events) if e["wiki_raw_path"])
        print("raw file:", raw)
        print("-" * 70)
        print(Path(raw).read_text())
        print("-" * 70)

        print("\nDEMO COMPLETE — full lifecycle proven with real files on disk.")


if __name__ == "__main__":
    main()
