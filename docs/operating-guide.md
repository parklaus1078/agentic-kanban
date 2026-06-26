# Operating Guide — Agent System v2

How to run the system day to day: seed, create a ticket, drive the worker/watcher, review,
and rerun. Commands assume the **local (no-Docker)** setup from the [README](../README.md)
with the API running on `http://localhost:8000`. Routes and JSON shapes are frozen in
**[API_CONTRACT.md](API_CONTRACT.md)**; component rationale is in
**[architecture.md](architecture.md)**.

Set a shell variable to keep the examples short:

```bash
API=http://localhost:8000
```

## 1. Seed

Creates the default board, the 17 personas, and the skill catalog. Idempotent — safe to
re-run.

```bash
curl -X POST $API/admin/seed
# From the repo root you can also use: make seed
```

Sanity check:

```bash
curl $API/health        # {"status":"ok"}
curl $API/boards        # [{ "id":1, "name":"Default Board", ... }]
curl $API/personas      # 17 personas
```

## 2. Create a ticket

A new ticket lands in `Triage/Ready`. `board_id` is required; the rest are optional.

```bash
curl -X POST $API/tickets -H 'Content-Type: application/json' -d '{
  "board_id": 1,
  "title": "Add health endpoint",
  "description_md": "Expose GET /health returning ok.",
  "acceptance_criteria_md": "- 200 with {\"status\":\"ok\"}",
  "assignee_persona": "Full Stack Developer",
  "priority": 3
}'
```

Note the returned `id` (used as `{ticket_id}` below) and `ticket_number` (e.g. `ASV2-0001`).

## 3. Move the ticket toward work

Transitions are validated server-side (see the status model in the README). Walk it to
`In Progress`:

```bash
curl -X POST $API/tickets/1/transition -H 'Content-Type: application/json' \
  -d '{"to_status":"Todo","actor":"Hermes"}'
curl -X POST $API/tickets/1/transition -H 'Content-Type: application/json' \
  -d '{"to_status":"In Progress","actor":"Hermes"}'
```

Each transition writes a status event and an LLM Wiki raw event (see section 8).

## 4. Navigator recommendation

Ask the Navigator for a persona/agent/model/skills recommendation; override any field if you
disagree.

```bash
# accept the recommendation
curl -X POST $API/tickets/1/navigator/recommend -H 'Content-Type: application/json' -d '{}'

# override persona + model (manual_override is recorded as true)
curl -X POST $API/tickets/1/navigator/recommend -H 'Content-Type: application/json' -d '{
  "override": { "persona": "CTO", "model": "Claude CLI Opus 4.8" }
}'
```

## 5. Create a run and drive worker + watcher

Creating a run enqueues it (`AgentRun.status = queued`, a `queue_item` appears). By default
the run uses the latest navigator decision.

```bash
# create the run (queued)
curl -X POST $API/tickets/1/runs -H 'Content-Type: application/json' -d '{"use_navigator": true}'

# worker tick: run -> running, adapter writes artifact + .agent_done.json sentinel
curl -X POST $API/admin/worker/tick

# watcher tick: detects sentinel, run -> success, ticket -> Reviewing, writes wiki event
curl -X POST $API/admin/watcher/tick
```

Inspect the run (artifacts + watcher events) and the queue:

```bash
curl $API/runs/1
curl $API/queue
```

In a long-running deployment the worker and watcher loops do this continuously; the
`/admin/*/tick` endpoints exist so you can step the lifecycle by hand in dev and the demo.

## 6. Review (and the rerun loop)

When the ticket is in `Reviewing`, Kay reviews it.

**Satisfied -> Completed:**

```bash
curl -X POST $API/tickets/1/review -H 'Content-Type: application/json' -d '{
  "satisfied": true,
  "comment_md": "LGTM",
  "actor": "Kay"
}'
```

**Not satisfied -> rerun:** the ticket goes back to `In Progress` and a new `AgentRun` is
created whose prompt includes your review comment. Then tick worker + watcher again.

```bash
curl -X POST $API/tickets/1/review -H 'Content-Type: application/json' -d '{
  "satisfied": false,
  "comment_md": "Return 200 not 201; add a test.",
  "actor": "Kay"
}'
curl -X POST $API/admin/worker/tick
curl -X POST $API/admin/watcher/tick
# review again until satisfied
```

The whole sequence is scripted in `scripts/demo.py` (`python scripts/demo.py`), which prints
each step and the real wiki raw path created.

## 7. Where artifacts and wiki raw files land

- **Agent artifacts + sentinel** — under the agent output dir, namespaced per ticket/run:
  - Claude runs: `/mnt/k/WRITTEN_BY_CLAUDE/asv2-<nnnn>/run-<n>/` (artifact + `.agent_done.json`)
  - Codex runs:  `/mnt/k/WRITTEN_BY_CODEX/asv2-<nnnn>/run-<n>/`
  - The run's `output_path` and each `artifact.path` point here.
- **LLM Wiki raw events** — one markdown file per status change under
  `/home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/`; the path is recorded
  on `StatusEvent.wiki_raw_path`. Format (frontmatter + `Ticket` / `Decision / Reason` /
  `Comments / Review` / `Result Summary` / `Artifacts` sections) is documented in the README.

Quick look at the latest raw events:

```bash
ls -lt /home/kay/llm_wiki/kay_second_brain/raw/decisions/agent-system-v2/ | head
```

## 8. Cron schedule (LLM Wiki ingest / audit)

Run by `app.scheduler_loop`; tracked as `wiki_sync_jobs`. Times are **KST (Asia/Seoul)**.

| Job    | Cadence            | What it does |
|--------|--------------------|--------------|
| ingest | daily, **02:00 KST** | Pull new `raw/decisions/agent-system-v2/` events into the wiki ingest pipeline (`ingest_status`). |
| audit  | **04:00 KST**, month-end | Reconcile/audit the month's events (`audit_status`). |

In the MVP these are **not** wired to a live cron — invoke the scheduler loop manually or via
`POST /wiki-sync/tickets/{ticket_id}/fork-raw` to force a raw fork, and inspect with
`GET /wiki-sync/jobs`. Wiring a real crontab/systemd timer is backlog.

## 9. Safety notes

- **Workspace allowlist.** Agents may only write under the configured output roots
  (`/mnt/k/WRITTEN_BY_CODEX`, `/mnt/k/WRITTEN_BY_CLAUDE`). Paths outside the allowlist are
  rejected before a run starts.
- **Output-path enforcement.** Each run's required `output_path` is computed by the system
  and passed into the prompt; the watcher only accepts artifacts/sentinels under that path,
  so a run can't claim files elsewhere.
- **No secrets in prompts.** Prompts are assembled from ticket fields, acceptance criteria,
  comments, persona, skills, and the review comment only — never credentials or tokens. Keep
  secrets out of ticket/comment bodies.
- **Approval gate for destructive tickets.** Tickets flagged destructive (and any run while
  `ASV2_AGENT_MODE=real`) require an explicit human transition out of `Triage/Ready` before
  work begins; the simulated adapter is the safe default.
- **Redaction hook.** A redaction pass runs over content before it is written to LLM Wiki raw
  events, so sensitive strings are scrubbed from the durable record. Review raw output if you
  handle regulated data.
