# Agent System v2 — Frozen API Contract (MVP)

> This is the single source of truth for the HTTP interface. The FastAPI backend
> implements exactly these routes/shapes; the React frontend consumes exactly these.
> Do not invent new shapes — if something is missing, treat the field as optional.

- Base URL (dev): `http://localhost:8000` (no `/api` prefix — paths are mounted at root).
- All bodies/responses are JSON. Timestamps are ISO-8601 UTC strings (e.g. `2026-06-26T00:52:23Z`).
- CORS is open for `http://localhost:5173` (Vite dev server) and `*` in MVP.
- Frontend reads base URL from `import.meta.env.VITE_API_BASE` (default `http://localhost:8000`).

## Enums

- **status names** (status_blocks, default board): `Triage/Ready`, `Todo`, `In Progress`, `Blocked`, `Reviewing`, `Completed`, `Canceled`.
- **agent**: `codex` | `claude`.
- **persona family**: `business` (Codex group) | `engineering` (Claude group).
- **agent_run.status**: `queued` | `running` | `success` | `failed` | `canceled`.
- **queue_item.state**: `queued` | `running` | `done` | `canceled`.
- **comment.author_type**: `human` | `agent` | `hermes` | `kay`.

## Object shapes

### Board
```json
{ "id": 1, "name": "Default Board", "description": "string|null",
  "created_at": "iso", "updated_at": "iso",
  "status_blocks": [StatusBlock]  // present on GET /boards/{id} and POST /boards
}
```

### StatusBlock
```json
{ "id": 1, "board_id": 1, "name": "Todo", "order_index": 1,
  "color": "#93c5fd", "is_agent_digestible": false, "is_terminal": false }
```

### Ticket
```json
{ "id": 1, "board_id": 1, "ticket_number": "ASV2-0001", "title": "string",
  "description_md": "string", "acceptance_criteria_md": "string",
  "status": "Todo", "status_block_id": 2,
  "assignee_persona": "Full Stack Developer|null", "priority": 3,
  "created_at": "iso", "updated_at": "iso",
  "started_at": "iso|null", "completed_at": "iso|null", "canceled_at": "iso|null" }
```

### TicketDetail (extends Ticket)
```json
{ ...Ticket,
  "comments": [Comment], "status_events": [StatusEvent],
  "runs": [AgentRun], "navigator_decision": NavigatorDecision|null }
```

### Comment
```json
{ "id": 1, "ticket_id": 1, "author_type": "kay", "author_name": "Kay",
  "body_md": "string", "body_latex_raw": "string|null",
  "is_digestible": true, "created_at": "iso" }
```

### StatusEvent
```json
{ "id": 1, "ticket_id": 1, "from_status": "Todo|null", "to_status": "In Progress",
  "actor": "Hermes", "reason_md": "string|null",
  "wiki_raw_path": "/home/kay/llm_wiki/.../ASV2-0001-...md|null", "created_at": "iso" }
```

### Persona
```json
{ "id": 1, "persona_name": "Full Stack Developer", "default_agent": "claude",
  "default_model": "Claude CLI Sonnet 4.6", "family": "engineering",
  "description": "string", "risk_level": "low", "is_active": true }
```

### Skill
```json
{ "id": 1, "name": "test-driven-development", "tags": ["testing","quality"],
  "compatible_personas": ["Full Stack Developer","QA(Unit test)"],
  "compatible_brains": ["claude","codex"], "description": "string" }
```

### NavigatorDecision
```json
{ "id": 1, "ticket_id": 1, "persona": "Full Stack Developer",
  "agent": "claude", "model": "Claude CLI Sonnet 4.6",
  "skills": ["test-driven-development","github-pr-workflow"],
  "confidence": 0.82, "reason": "string",
  "alternatives": ["Codex CLI gpt 5.5: PM/QA(E2E) review angle"],
  "manual_override": false, "created_at": "iso" }
```

### AgentRun
```json
{ "id": 1, "ticket_id": 1, "run_number": 1, "agent": "claude",
  "model": "Claude CLI Sonnet 4.6", "persona": "Full Stack Developer",
  "prompt_md": "string", "skills": ["..."], "plugins": [],
  "output_path": "/mnt/k/WRITTEN_BY_CLAUDE/asv2-0001/run-1|null",
  "status": "success", "process_id": "string|null",
  "started_at": "iso|null", "finished_at": "iso|null", "error": "string|null" }
```

### AgentRunDetail (extends AgentRun)
```json
{ ...AgentRun, "artifacts": [Artifact], "watcher_events": [WatcherEvent] }
```

### Artifact
```json
{ "id": 1, "run_id": 1, "path": "string", "mime_type": "text/markdown",
  "author_name": "Full Stack Developer", "summary": "string",
  "checksum": "sha256hex", "created_at": "iso" }
```

### WatcherEvent
```json
{ "id": 1, "run_id": 1, "event_type": "sentinel_detected",
  "payload": { "any": "json" }, "observed_at": "iso" }
```

### QueueItem
```json
{ "id": 1, "ticket_id": 1, "ticket_number": "ASV2-0001", "ticket_title": "string",
  "run_id": 1, "order_index": 0, "state": "queued",
  "cancel_requested": false, "locked_by": "string|null",
  "queued_at": "iso", "started_at": "iso|null" }
```

### WikiSyncJob
```json
{ "id": 1, "ticket_id": 1, "raw_path": "string", "ingest_status": "pending",
  "audit_status": "pending", "scheduled_at": "iso|null", "completed_at": "iso|null",
  "created_at": "iso" }
```

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | – | `{ "status": "ok" }` |
| POST | `/admin/seed` | – | `{ "board": Board, "personas": int, "skills": int }` (idempotent) |
| GET | `/boards` | – | `[Board]` |
| POST | `/boards` | `{ name, description?, seed_default_statuses? (default true) }` | `Board` (with status_blocks) |
| GET | `/boards/{board_id}` | – | `Board` (with status_blocks) |
| GET | `/boards/{board_id}/status-blocks` | – | `[StatusBlock]` |
| POST | `/boards/{board_id}/status-blocks` | `{ name, color?, is_agent_digestible?, order_index?, is_terminal? }` | `StatusBlock` |
| PATCH | `/status-blocks/{id}` | `{ name?, color?, is_agent_digestible?, order_index? }` | `StatusBlock` |
| DELETE | `/status-blocks/{id}` | – | `204` (409 if tickets reference it) |
| GET | `/boards/{board_id}/tickets` | – | `[Ticket]` |
| POST | `/tickets` | `{ board_id, title, description_md?, acceptance_criteria_md?, assignee_persona?, priority? }` | `Ticket` |
| GET | `/tickets/{ticket_id}` | – | `TicketDetail` |
| PATCH | `/tickets/{ticket_id}` | `{ title?, description_md?, acceptance_criteria_md?, assignee_persona?, priority? }` | `Ticket` |
| GET | `/tickets/{ticket_id}/comments` | – | `[Comment]` |
| POST | `/tickets/{ticket_id}/comments` | `{ author_type, author_name, body_md, is_digestible? }` | `Comment` |
| POST | `/tickets/{ticket_id}/transition` | `{ to_status, actor?, reason_md? }` | `{ ticket: Ticket, status_event: StatusEvent }` |
| POST | `/tickets/{ticket_id}/navigator/recommend` | `{ override?: { persona?, agent?, model?, skills? } }` | `NavigatorDecision` |
| POST | `/tickets/{ticket_id}/runs` | `{ use_navigator? (default true), persona?, agent?, model?, skills? }` | `AgentRun` |
| GET | `/runs/{run_id}` | – | `AgentRunDetail` |
| POST | `/runs/{run_id}/cancel` | – | `AgentRun` |
| GET | `/queue` | – | `[QueueItem]` (ordered by order_index) |
| PATCH | `/queue/reorder` | `{ ordered_ids: [int] }` | `[QueueItem]` |
| POST | `/queue/{queue_item_id}/cancel` | – | `QueueItem` |
| POST | `/tickets/{ticket_id}/review` | `{ satisfied: bool, comment_md?, actor? }` | `{ ticket: Ticket, rerun: AgentRun|null }` |
| GET | `/personas` | – | `[Persona]` |
| GET | `/skills` | – | `[Skill]` |
| GET | `/wiki-sync/jobs` | – | `[WikiSyncJob]` |
| POST | `/wiki-sync/tickets/{ticket_id}/fork-raw` | `{ note_md? }` | `{ raw_path: string }` |
| POST | `/admin/worker/tick` | – | `{ processed: [run_id] }` (advances queued runs → running, executes adapter) |
| POST | `/admin/watcher/tick` | – | `{ detected: [run_id] }` (detects completion → Reviewing/Blocked) |

### Lifecycle (how the UI drives a demo)
1. `POST /admin/seed` → default board + personas + skills.
2. `POST /tickets` (board_id) → ticket in `Triage/Ready`.
3. `POST /tickets/{id}/transition {to_status:"Todo"}` then `{to_status:"In Progress"}`.
4. `POST /tickets/{id}/navigator/recommend` → persona/agent/model/skills suggestion (overridable).
5. `POST /tickets/{id}/runs` → creates AgentRun (status `queued`) + QueueItem.
6. `POST /admin/worker/tick` → run becomes `running`, adapter writes artifact + `.agent_done.json` sentinel under the agent output dir.
7. `POST /admin/watcher/tick` → detects sentinel, creates artifacts + watcher_events, run `success`, ticket → `Reviewing`, writes wiki raw event.
8. `POST /tickets/{id}/review {satisfied:true}` → ticket `Completed` (or `{satisfied:false, comment_md}` → ticket back to `In Progress` + new rerun AgentRun whose prompt includes the review comment).

Every transition writes a markdown raw event file under
`/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/` and records `wiki_raw_path`.
