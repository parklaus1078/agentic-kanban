# Agent System v2 — Web (SPA)

React 18 + TypeScript + Vite single-page operations console for Agent System v2.
Consumes the frozen API contract in [`../../docs/API_CONTRACT.md`](../../docs/API_CONTRACT.md).

## Commands

```bash
npm install
npm run dev        # vite dev server (http://localhost:5173)
npm run build      # tsc -b && vite build
npm run typecheck  # tsc --noEmit
npm run preview    # preview the production build
```

## Configuration

- `VITE_API_BASE` — backend base URL. Defaults to `http://localhost:8000`.
  Example: `VITE_API_BASE=http://localhost:8000 npm run dev`.

## What's implemented

1. Kanban board — one column per status block; per-card status `<select>` and
   native HTML5 drag-and-drop both call `POST /tickets/{id}/transition`.
2. Status block management — list / add / delete blocks and toggle
   `is_agent_digestible`.
3. Ticket create modal + edit drawer — title, `description_md`,
   `acceptance_criteria_md`, `assignee_persona` (from `GET /personas`), priority.
4. Markdown rendering (via `marked`) for description, acceptance criteria and
   comments. Comments list + add.
5. Navigator panel — recommend + override (persona / agent / model / skills).
6. Queue panel — order/state/cancel_requested, reorder (up/down), cancel.
7. Agent run monitor — runs, run detail (artifacts + watcher events), plus
   "Worker tick" / "Watcher tick" buttons to drive the simulated loop.
8. Review panel — Satisfied/Complete and Not-satisfied/Rerun (with comment).

## LaTeX handling (backlog: KaTeX)

LaTeX math spans (`$...$`, `$$...$$`) are **preserved exactly as written**: they
are pulled out before Markdown parsing so Markdown cannot mangle them, then
re-inserted as raw text in `<span class="latex-raw">`. Rendering the preserved
math with KaTeX is a documented backlog item — see `src/markdown.ts` (the restore
callback is the single drop-in point for `katex.renderToString`).

## Layout of source

- `src/api.ts` — single typed API client, one function per endpoint, interfaces
  mirroring the contract (snake_case fields).
- `src/markdown.ts` — `marked`-based renderer with LaTeX preservation.
- `src/App.tsx` — top-level state + layout.
- `src/components/*` — one component per panel.
