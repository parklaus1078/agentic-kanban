# Architecture — Agent System v2

This describes the components, data model, and the design decisions behind the MVP.
The HTTP surface is frozen in **[API_CONTRACT.md](API_CONTRACT.md)** — that file wins on any
route/field discrepancy. For setup commands see the [README](../README.md); for day-to-day
operation see the [operating guide](operating-guide.md).

## Components

| Component       | Where                                   | Responsibility |
|-----------------|-----------------------------------------|----------------|
| **Web**         | `apps/web` (React + TS + Vite, :5173)   | Kanban board, ticket drawer (markdown fields), navigator panel, queue panel, run monitor, review panel. Reads the API base from `VITE_API_BASE`. |
| **API**         | `apps/api/app` (FastAPI, `app.main:app`, :8000) | All routes in the contract: board/ticket/comment CRUD, transitions, navigator recommend, run creation, queue, review, wiki fork. Owns the DB schema and enforces status transitions. |
| **Postgres**    | compose service (`infra/`)              | System of record in the Docker path. In local dev the API falls back to SQLite. |
| **Navigator**   | module inside `apps/api/app`            | Classifies a ticket into a persona, maps to the persona's default agent/model, attaches a skill set, and records confidence / reason / alternatives / `manual_override`. Pure decision logic — no side effects beyond writing a `navigator_decisions` row. |
| **Worker / Adapter** | `app.worker_loop`; launcher `services/worker/` | Pulls `queued` runs, flips them to `running`, builds the agent prompt, and invokes the adapter. The adapter is either the **simulated** one (`ASV2_AGENT_MODE=sim`, deterministic) or the **real** Codex/Claude CLI (`ASV2_AGENT_MODE=real`). It writes artifact files and a `.agent_done.json` sentinel into the agent output dir, then stops. It does **not** transition the ticket. |
| **Watcher**     | `app.watcher_loop`; launcher `services/watcher/` | Detects completion by reading the `.agent_done.json` sentinel (and artifact changes). On success it creates `artifacts` + `watcher_events` rows, marks the run `success`, transitions the ticket to `Reviewing`, and writes a status event + wiki raw event. On failure it marks the run `failed` and moves the ticket to `Blocked`. |
| **Scheduler**   | `app.scheduler_loop`                    | Runs the LLM Wiki ingest/audit jobs on a cron cadence (ingest daily 02:00 KST, audit 04:00 KST month-end). Tracked as `wiki_sync_jobs`. Not wired to a live cron in the MVP. |
| **LLM Wiki Sync** | code in `apps/api/app` + scheduler     | Writes raw event markdown (frontmatter + sections) under `/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/` on every status change and records `wiki_raw_path`. Only raw sources are written — synthesized `wiki/` pages are never touched. |

In dev, `POST /admin/worker/tick` and `POST /admin/watcher/tick` run one iteration of the
worker/watcher logic inline, so you can drive the full lifecycle without the loop processes.

## Data model summary

Tables and their load-bearing columns (see the contract for exact JSON field names):

| Table                 | Key columns |
|-----------------------|-------------|
| `boards`              | `id`, `name`, `description`, `created_at`, `updated_at` |
| `board_templates`     | template definitions used to seed default status sets |
| `status_blocks`       | `id`, `board_id`, `name`, `order_index`, `color`, `is_agent_digestible`, `is_terminal` |
| `tickets`             | `id`, `board_id`, `ticket_number` (`ASV2-NNNN`), `title`, `description_md`, `acceptance_criteria_md`, `status`, `status_block_id`, `assignee_persona`, `priority`, `created_at`, `updated_at`, `started_at`, `completed_at`, `canceled_at` |
| `comments`            | `id`, `ticket_id`, `author_type` (`human`/`agent`/`hermes`/`kay`), `author_name`, `body_md`, `body_latex_raw`, `is_digestible`, `created_at` |
| `status_events`       | `id`, `ticket_id`, `from_status`, `to_status`, `actor`, `reason_md`, `wiki_raw_path`, `created_at` |
| `personas`            | `id`, `persona_name`, `default_agent`, `default_model`, `family`, `description`, `risk_level`, `is_active` |
| `skills`              | `id`, `name`, `tags`, `compatible_personas`, `compatible_brains`, `description` |
| `navigator_decisions` | `id`, `ticket_id`, `persona`, `agent`, `model`, `skills`, `confidence`, `reason`, `alternatives`, `manual_override`, `created_at` |
| `agent_runs`          | `id`, `ticket_id`, `run_number`, `agent`, `model`, `persona`, `prompt_md`, `skills`, `plugins`, `output_path`, `status` (`queued`/`running`/`success`/`failed`/`canceled`), `process_id`, `started_at`, `finished_at`, `error` |
| `queue_items`         | `id`, `ticket_id`, `run_id`, `order_index`, `state` (`queued`/`running`/`done`/`canceled`), `cancel_requested`, `locked_by`, `queued_at`, `started_at` |
| `artifacts`           | `id`, `run_id`, `path`, `mime_type`, `author_name`, `summary`, `checksum`, `created_at` |
| `watcher_events`      | `id`, `run_id`, `event_type`, `payload` (json), `observed_at` |
| `wiki_sync_jobs`      | `id`, `ticket_id`, `raw_path`, `ingest_status`, `audit_status`, `scheduled_at`, `completed_at`, `created_at` |

Relationships: a `board` has many `status_blocks` and `tickets`; a `ticket` has many
`comments`, `status_events`, `agent_runs`, and (at most one current) `navigator_decision`;
an `agent_run` has many `artifacts` and `watcher_events` and exactly one `queue_item`.

## Worker / watcher separation of concerns

The two roles are deliberately split so completion detection never blocks on execution and a
crashed worker can't leave a ticket half-transitioned:

- **Worker = execute + write sentinel.** It owns prompt assembly and adapter invocation,
  produces artifacts plus a single authoritative `.agent_done.json`, and updates only the
  run's own execution state (`queued -> running`, then the sentinel records the outcome). It
  never touches ticket status. This keeps the side that may call out to a real CLI (slow,
  flaky, quota-bound) isolated.
- **Watcher = detect + transition.** It is the only writer of ticket status for agent runs.
  It polls for the sentinel/artifacts, records `watcher_events`, finalizes the run
  (`success`/`failed`), moves the ticket (`Reviewing` on success, `Blocked` on failure), and
  emits the status event + wiki raw event.

Because the sentinel file is the contract between them, the worker and watcher can run as
separate processes (compose), as separate loops, or be driven one tick at a time in tests
and the demo — without changing the logic.

## Why SQLite by default, Postgres in compose

- **Local dev / tests / demo use SQLite.** With `DATABASE_URL` unset the API opens a local
  SQLite file and creates the schema at startup. Zero external services means the no-Docker
  path, `pytest`, and `scripts/demo.py` run anywhere with just Python 3.11 — which matters in
  this environment, where no Docker daemon is available. Tests use an isolated SQLite DB.
- **Compose uses Postgres.** The product target is PostgreSQL, so the compose stack sets
  `DATABASE_URL` to the `postgres` service. The ORM layer (SQLAlchemy) is the same in both;
  only the connection string changes. JSON-valued columns (`skills`, `payload`,
  `alternatives`, etc.) work on both backends.

This gives a frictionless default for development and verification while keeping the
production-shaped database one `docker compose up` away.
