# Agent System v2

A Kanban-centered multi-agent operations MVP. You turn brain dumps or requests into
Kanban tickets; **Hermes** orchestrates the board; the **Navigator** classifies each
ticket into a persona and picks the agent, model, and skill/plugin set; a **worker**
dispatches the run to the **Codex CLI** or **Claude CLI** (or a deterministic simulated
adapter for quota-free demos); a **Watcher** detects completion via a sentinel file and
moves the ticket to `Reviewing`; **Kay** reviews and either marks it `Completed` or sends
it back into a rerun with the review comment folded into the next prompt. Every status
change writes an LLM Wiki raw event (markdown with frontmatter) under
`/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/`.

The HTTP interface is frozen — see **[docs/API_CONTRACT.md](docs/API_CONTRACT.md)** for the
authoritative routes and JSON shapes. Background and rationale live in
**[docs/architecture.md](docs/architecture.md)**; day-to-day operation in
**[docs/operating-guide.md](docs/operating-guide.md)**.

---

## Architecture

```
                              HOST  (WSL2 / Linux)
 +--------------------------------------------------------------------------------+
 |  Browser                                                                       |
 |     |  http                                                                    |
 |     v                                                                          |
 |  +-------------+    VITE_API_BASE      +-----------------------------+         |
 |  | web         | --------------------> | api  (FastAPI)              |         |
 |  | React+Vite  |    JSON over HTTP     | app.main:app        :8000   |         |
 |  | :5173       | <-------------------- |                             |         |
 |  +-------------+                       +----+-----------------+------+         |
 |                                             |                 |                |
 |                                  SQLAlchemy |                 | enqueue runs   |
 |                                             v                 v                |
 |                                     +---------------+   +------------------+   |
 |                                     | Postgres      |   | queue_items      |   |
 |                                     | (compose)     |   | (rows in the DB) |   |
 |                                     | SQLite (dev)  |   +---------+--------+    |
 |                                     +-------+-------+             |             |
 |                                             ^                     |             |
 |                                             |  read / write       |            |
 |        +------------------------------------+---------------------+            |
 |        |                                    |                     |            |
 |  +-----+--------+                  +--------+-------+      +-------+--------+   |
 |  | worker       |                  | watcher        |      | scheduler      |  |
 |  | app.worker_  |                  | app.watcher_   |      | app.scheduler_ |  |
 |  | loop         |                  | loop           |      | loop           |  |
 |  +-----+--------+                  +--------+-------+      +-------+--------+   |
 |        | runs adapter,                     | detects sentinel,     | cron      |
 |        | writes artifact +                 | run->success,         | ingest /  |
 |        | .agent_done.json sentinel         | ticket->Reviewing,    | audit     |
 |        |                                   | writes wiki event     |           |
 +--------|-----------------------------------|-----------------------|----------+
          |                                   |                       |
   host bind mounts:                          |                       |
   /mnt/k/WRITTEN_BY_CODEX   <--- worker, codex runs ----+            |
   /mnt/k/WRITTEN_BY_CLAUDE  <--- worker, claude runs ---+            |
   /home/kay/llm_wiki        <--- watcher + scheduler raw events -----+
```

`worker`, `watcher`, and `scheduler` are the same backend package run as different loop
entrypoints (`app.worker_loop`, `app.watcher_loop`, `app.scheduler_loop`). In dev you can
drive them on demand via `POST /admin/worker/tick` and `POST /admin/watcher/tick` instead
of running the loops.

---

## Repository layout

```
apps/api/        FastAPI backend (python package: apps/api/app)
                 entrypoints: app.main:app, app.worker_loop, app.watcher_loop, app.scheduler_loop
apps/web/        React + TypeScript + Vite frontend
services/worker/ thin launcher that invokes app.worker_loop
services/watcher/thin launcher that invokes app.watcher_loop
infra/           docker-compose.yml + Dockerfile.api + Dockerfile.web
scripts/         demo.py end-to-end lifecycle script
docs/            API_CONTRACT.md (frozen), architecture.md, operating-guide.md
```

Backend tests live in `apps/api/tests/` (run with `cd apps/api && pytest`).

---

## Run with Docker Compose

Requires a running Docker daemon with Compose v2. Brings up `web`, `api`, `postgres`,
`worker`, `watcher`, and `scheduler`, mounting the host artifact dirs and the LLM Wiki.
Run everything **from the repo root** (the Makefile and compose project dir live there):

```bash
make up      # docker compose up -d --build  (full stack)
make seed    # POST /admin/seed  (board + personas + skills, idempotent)
```

The raw equivalents (also from the repo root) are:

```bash
docker compose -f infra/docker-compose.yml --project-directory . up -d --build
curl -X POST http://localhost:8000/admin/seed
```

- Web UI: <http://localhost:5173>
- API:    <http://localhost:8000>  (health: `curl http://localhost:8000/health`)

---

## Run locally WITHOUT Docker

This is the supported path in the current dev environment (no Docker daemon). Requires
**Python 3.11** and **Node 18+** (tested with Node 22).

### 1. Backend (FastAPI on :8000)

```bash
cd /mnt/k/WSL_volume/agent-system-v2
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt

cd apps/api
uvicorn app.main:app --reload
```

`DATABASE_URL` is unset by default, so the API uses a local **SQLite** file (created on
first run). The schema is created automatically at startup. Seed once the server is up:

```bash
curl -X POST http://localhost:8000/admin/seed
```

### 2. Frontend (Vite on :5173)

```bash
cd /mnt/k/WSL_volume/agent-system-v2/apps/web
npm install
npm run dev
```

Vite serves on <http://localhost:5173> and talks to the API at `VITE_API_BASE`
(default `http://localhost:8000`). To point at a different API:

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

---

## Run tests

```bash
cd /mnt/k/WSL_volume/agent-system-v2/apps/api
pytest
```

Tests run against an isolated SQLite database and cover the core lifecycle (seed, ticket
create, transitions, navigator recommend, run + worker tick + watcher tick, review/rerun).

---

## Run the demo lifecycle

Self-contained: runs the whole lifecycle **in-process** via FastAPI's `TestClient`, so no
running server is needed — only the backend deps installed. Prints each lifecycle step plus
the real artifact + wiki raw file paths it created (using a dedicated demo SQLite DB).

```bash
cd /mnt/k/WSL_volume/agent-system-v2
source .venv/bin/activate          # backend deps (see "Run locally WITHOUT Docker")
python scripts/demo.py
```

It exercises: seed -> create ticket -> `Todo` -> `In Progress` -> navigator recommend ->
create run -> worker tick (artifact + `.agent_done.json`) -> watcher tick (`Reviewing`) ->
review NOT satisfied (rerun with the comment folded into the next prompt) -> drive rerun ->
review satisfied (`Completed`), and echoes the artifact path under
`/mnt/k/WRITTEN_BY_*` and the wiki raw path under
`/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/`.

---

## Persona / agent mapping

Seeded as `personas` rows and exposed via `GET /personas`. The Navigator first classifies a
ticket into a persona, then uses the persona's default agent/model (overridable per run).

| Persona                | Agent  | Default model(s)                  | Family      |
|------------------------|--------|-----------------------------------|-------------|
| PM                     | codex  | Codex CLI gpt 5.5                 | business    |
| QA(E2E)                | codex  | Codex CLI gpt 5.5                 | business    |
| Marketer               | codex  | Codex CLI gpt 5.5                 | business    |
| Accountant             | codex  | Codex CLI gpt 5.5                 | business    |
| Strategist             | codex  | Codex CLI gpt 5.5                 | business    |
| CS Manager             | codex  | Codex CLI gpt 5.5                 | business    |
| Researcher             | codex  | Codex CLI gpt 5.5                 | business    |
| CTO                    | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| Full Stack Developer   | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| DevOps                 | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| Android Engineer       | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| iOS Engineer           | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| AI Engineer            | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| MLOps                  | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| Data Engineer          | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| QA(Unit test)          | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |
| SecOps                 | claude | Claude CLI Opus 4.8 / Sonnet 4.6  | engineering |

- `agent` enum: `codex` | `claude`.
- `family` enum: `business` (Codex group) | `engineering` (Claude group).

---

## Status model + allowed transitions

Default `status_blocks` (board "Default Board"):
`Triage/Ready`, `Todo`, `In Progress`, `Blocked`, `Reviewing`, `Completed`, `Canceled`.

Allowed transitions (enforced by `POST /tickets/{id}/transition`):

```
Triage/Ready --> Todo --> In Progress --> Reviewing --> Completed
                              ^   |
                              |   v
                          In Progress <--> Blocked
Reviewing --> In Progress            (Kay not satisfied -> rerun)
<any non-terminal> --> Canceled
```

- Happy path: `Triage/Ready -> Todo -> In Progress -> Reviewing -> Completed`.
- `In Progress -> Blocked -> In Progress` for blocked work.
- `Reviewing -> In Progress` when Kay is not satisfied (creates a rerun `AgentRun`).
- Any non-terminal status -> `Canceled`.
- `Completed` and `Canceled` are terminal in the MVP (admin reopen is backlog).

The watcher moves a run's ticket to `Reviewing` on success, or `Blocked` on failure.

---

## Output contract and LLM Wiki raw event

### Sentinel: `.agent_done.json`

Every run writes its artifact(s) plus a sentinel under the agent output dir
(`/mnt/k/WRITTEN_BY_CODEX/...` or `/mnt/k/WRITTEN_BY_CLAUDE/...`). The watcher reads it:

```json
{
  "run_id": 1,
  "ticket_id": 1,
  "ticket_number": "ASV2-0001",
  "agent": "claude",
  "model": "Claude CLI Sonnet 4.6",
  "persona": "Full Stack Developer",
  "status": "success",
  "summary": "string",
  "artifacts": ["/mnt/k/WRITTEN_BY_CLAUDE/asv2-0001/run-1/result.md"],
  "author_name": "Full Stack Developer",
  "finished_at": "2026-06-26T00:52:23Z"
}
```

`status` is `success` | `failed`.

### Wiki raw event (one markdown file per status change)

Written under `/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/`; the
path is recorded on the `StatusEvent.wiki_raw_path` field. Format:

```markdown
---
type: agent_ticket_event
ticket_id: 1
ticket_number: ASV2-0001
status_from: In Progress
status_to: Reviewing
actor: Watcher
persona: Full Stack Developer
agent: claude
model: Claude CLI Sonnet 4.6
run_id: 1
artifacts:
  - /mnt/k/WRITTEN_BY_CLAUDE/asv2-0001/run-1/result.md
created_at: 2026-06-26T00:52:23Z
---

## Ticket
<title + description>

## Decision / Reason
<navigator persona/agent/model/skills + reason, or transition reason>

## Comments / Review
<relevant comments and Kay's review note>

## Result Summary
<run summary from the sentinel>

## Artifacts
- /mnt/k/WRITTEN_BY_CLAUDE/asv2-0001/run-1/result.md
```

Only raw sources are written; synthesized pages under
`/home/kay/llm_wiki/kay_second_brain/wiki/` are never edited by this MVP.

---

## Configuration

| Variable          | Default                                 | Purpose                                              |
|-------------------|-----------------------------------------|------------------------------------------------------|
| `DATABASE_URL`    | local SQLite file                       | DB connection. Compose sets a Postgres URL.          |
| `VITE_API_BASE`   | `http://localhost:8000`                 | Frontend -> API base URL (read at build/dev time).   |
| `ASV2_AGENT_MODE` | `simulated`                             | `simulated` = deterministic adapter (no model quota); `real` = invoke Codex/Claude CLI. |

Output directories default to `/mnt/k/WRITTEN_BY_CODEX` and `/mnt/k/WRITTEN_BY_CLAUDE`; the
wiki raw dir defaults to `/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/`.

---

## Known limitations / backlog

- **Docker compose validated by config only.** The dev environment has no Docker daemon, so
  the compose path was config-checked, not run end to end. The local (no-Docker) path is the
  exercised one.
- **Real CLI adapter is opt-in.** Default `ASV2_AGENT_MODE=simulated` uses a deterministic
  simulated adapter (no model quota burned). Set `ASV2_AGENT_MODE=real` to invoke the actual
  Codex/Claude CLI (configure `ASV2_CODEX_CMD_TEMPLATE` / `ASV2_CLAUDE_CMD_TEMPLATE`).
- **Cron not scheduled live.** Ingest/audit scripts exist behind `app.scheduler_loop` but are
  not wired to a live cron in dev. Intended schedule: wiki ingest daily 02:00 KST, audit
  04:00 KST at month-end (see operating-guide.md).
- **KaTeX rendering is optional.** Comments carry `body_latex_raw`; client-side math rendering
  is a nice-to-have, not required for the MVP.
- **Status-block editing is minimal.** Default statuses are seeded; add/delete/digest-toggle
  endpoints exist but the board UI for them is basic.
- **No auth / multi-tenant / K8s.** Out of scope for the MVP by design.