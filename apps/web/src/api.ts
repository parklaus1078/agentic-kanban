/**
 * Typed API client for Agent System v2.
 *
 * Mirrors docs/API_CONTRACT.md exactly. One function per endpoint, and a
 * TypeScript interface per object shape. Field names are snake_case to match
 * the frozen contract verbatim.
 *
 * Base URL is read from import.meta.env.VITE_API_BASE (default localhost:8000).
 */

export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

/* ------------------------------------------------------------------ */
/* Enums                                                               */
/* ------------------------------------------------------------------ */

export type AgentName = 'codex' | 'claude';
export type PersonaFamily = 'business' | 'engineering';
export type AgentRunStatus =
  | 'queued'
  | 'running'
  | 'success'
  | 'failed'
  | 'canceled';
export type QueueState = 'queued' | 'running' | 'done' | 'canceled';
export type AuthorType = 'human' | 'agent' | 'hermes' | 'kay';

/** Default board status names (from the contract). */
export const DEFAULT_STATUS_NAMES = [
  'Triage/Ready',
  'Todo',
  'In Progress',
  'Blocked',
  'Reviewing',
  'Completed',
  'Canceled',
] as const;

/* ------------------------------------------------------------------ */
/* Object shapes                                                       */
/* ------------------------------------------------------------------ */

export interface StatusBlock {
  id: number;
  board_id: number;
  name: string;
  order_index: number;
  color: string;
  is_agent_digestible: boolean;
  digest_policy?: string; // "none" | "agent_execute" — entering this status triggers a run
  is_terminal: boolean;
}

export interface Board {
  id: number;
  project_id?: number | null;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  status_blocks?: StatusBlock[];
}

export interface Project {
  id: number;
  slug: string;
  title: string;
  description: string | null;
  board_template_id: number | null;
  status: string; // "active" | "archived"
  board_id: number | null;
  created_at: string;
}

export interface BoardTemplate {
  id: number;
  name: string;
  default_statuses_json: string[];
  default_digest_policy: string;
}

export interface CreateProjectBody {
  title: string;
  slug?: string;
  description?: string | null;
  board_template_id?: number | null;
}

export interface UpdateProjectBody {
  title?: string;
  slug?: string;
  description?: string | null;
}

// ---- Phase 5/6/7/8 UI shapes ----
export interface ModelInfo {
  id: string;
  display: string;
  latest: boolean;
  default: boolean;
  effort: string[];
}
export interface ModelsForBrain {
  brain: string;
  default: string;
  models: ModelInfo[];
}
export interface PermissionPreset {
  key: string;
  label: string;
  claude_mode: string;
  codex_sandbox: string;
  codex_approval: string;
}
export interface PermissionProfile {
  brain: string;
  preset: string;
  allow: string[];
  deny: string[];
  flags: string[];
}
export interface SubdivisionProposal {
  id: number;
  parent_ticket_id: number;
  proposed_children_json: {
    title: string;
    description_md: string;
    acceptance_criteria_md: string;
  }[];
  status: string;
  created_by: string;
  created_at: string;
}
export interface MemoryHit {
  wiki_path: string;
  chunk: string;
  outcome: string | null;
  score: number;
}
export interface GeneratedSkill {
  id: number;
  slug: string;
  kind: string;
  suggested_ref: string | null;
  status: string;
  risk_level: string;
  approved_by: string | null;
  source_concept_path: string | null;
  body_md: string;
}
export interface RunLog {
  offset: number;
  content: string;
  eof: boolean;
}

export interface Ticket {
  id: number;
  board_id: number;
  ticket_number: string;
  title: string;
  description_md: string;
  acceptance_criteria_md: string;
  status: string;
  status_block_id: number;
  assignee_persona: string | null;
  priority: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  canceled_at: string | null;
  parent_ticket_id?: number | null;
  auto_complete_parent?: boolean;
}

export interface Comment {
  id: number;
  ticket_id: number;
  author_type: AuthorType;
  author_name: string;
  body_md: string;
  body_latex_raw: string | null;
  is_digestible: boolean;
  created_at: string;
}

export interface StatusEvent {
  id: number;
  ticket_id: number;
  from_status: string | null;
  to_status: string;
  actor: string;
  reason_md: string | null;
  wiki_raw_path: string | null;
  created_at: string;
}

export interface Persona {
  id: number;
  persona_name: string;
  default_agent: AgentName;
  default_model: string;
  family: PersonaFamily;
  description: string;
  risk_level: string;
  is_active: boolean;
}

export interface Skill {
  id: number;
  name: string;
  tags: string[];
  compatible_personas: string[];
  compatible_brains: string[];
  description: string;
}

export interface NavigatorDecision {
  id: number;
  ticket_id: number;
  persona: string;
  agent: AgentName;
  model: string;
  skills: string[];
  confidence: number;
  reason: string;
  alternatives: string[];
  manual_override: boolean;
  created_at: string;
}

export interface AgentRun {
  id: number;
  ticket_id: number;
  run_number: number;
  agent: AgentName;
  model: string;
  persona: string;
  prompt_md: string;
  skills: string[];
  plugins: string[];
  output_path: string | null;
  status: AgentRunStatus;
  process_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface Artifact {
  id: number;
  run_id: number;
  path: string;
  mime_type: string;
  author_name: string;
  summary: string;
  checksum: string;
  created_at: string;
}

export interface WatcherEvent {
  id: number;
  run_id: number;
  event_type: string;
  payload: Record<string, unknown>;
  observed_at: string;
}

export interface AgentRunDetail extends AgentRun {
  artifacts: Artifact[];
  watcher_events: WatcherEvent[];
}

export interface QueueItem {
  id: number;
  ticket_id: number;
  ticket_number: string;
  ticket_title: string;
  run_id: number;
  order_index: number;
  state: QueueState;
  cancel_requested: boolean;
  locked_by: string | null;
  queued_at: string;
  started_at: string | null;
}

export interface WikiSyncJob {
  id: number;
  ticket_id: number;
  raw_path: string;
  ingest_status: string;
  audit_status: string;
  scheduled_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  comments: Comment[];
  status_events: StatusEvent[];
  runs: AgentRun[];
  navigator_decision: NavigatorDecision | null;
}

/* ------------------------------------------------------------------ */
/* Request bodies                                                      */
/* ------------------------------------------------------------------ */

export interface CreateBoardBody {
  name: string;
  description?: string;
  seed_default_statuses?: boolean;
}

export interface CreateStatusBlockBody {
  name: string;
  color?: string;
  is_agent_digestible?: boolean;
  order_index?: number;
  is_terminal?: boolean;
}

export interface UpdateStatusBlockBody {
  name?: string;
  color?: string;
  is_agent_digestible?: boolean;
  order_index?: number;
}

export interface CreateTicketBody {
  board_id: number;
  title: string;
  description_md?: string;
  acceptance_criteria_md?: string;
  assignee_persona?: string | null;
  priority?: number;
}

export interface UpdateTicketBody {
  title?: string;
  description_md?: string;
  acceptance_criteria_md?: string;
  assignee_persona?: string | null;
  priority?: number;
}

export interface CreateCommentBody {
  author_type: AuthorType;
  author_name: string;
  body_md: string;
  is_digestible?: boolean;
}

export interface TransitionBody {
  to_status: string;
  actor?: string;
  reason_md?: string;
}

export interface NavigatorOverride {
  persona?: string;
  agent?: AgentName;
  model?: string;
  skills?: string[];
}

export interface RecommendBody {
  override?: NavigatorOverride;
}

export interface CreateRunBody {
  use_navigator?: boolean;
  persona?: string;
  agent?: AgentName;
  model?: string;
  skills?: string[];
}

export interface ReorderQueueBody {
  ordered_ids: number[];
}

export interface ReviewBody {
  satisfied: boolean;
  comment_md?: string;
  actor?: string;
}

export interface ForkRawBody {
  note_md?: string;
}

/* ------------------------------------------------------------------ */
/* Response envelopes                                                  */
/* ------------------------------------------------------------------ */

export interface TransitionResult {
  ticket: Ticket;
  status_event: StatusEvent;
}

export interface ReviewResult {
  ticket: Ticket;
  rerun: AgentRun | null;
}

export interface SeedResult {
  board: Board;
  personas: number;
  skills: number;
}

export interface WorkerTickResult {
  processed: number[];
}

export interface WatcherTickResult {
  detected: number[];
}

export interface ForkRawResult {
  raw_path: string;
}

/* ------------------------------------------------------------------ */
/* HTTP plumbing                                                       */
/* ------------------------------------------------------------------ */

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, message: string, detail: string) {
    super(detail ? `${message}: ${detail}` : message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    throw new ApiError(0, `Network error calling ${method} ${path}`, msg);
  }

  if (!res.ok) {
    let detail = '';
    try {
      detail = await res.text();
    } catch {
      /* ignore body read errors */
    }
    throw new ApiError(res.status, `${method} ${path} (${res.status})`, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    const text = await res.text();
    return text as unknown as T;
  }
  return (await res.json()) as T;
}

/* ------------------------------------------------------------------ */
/* Endpoints                                                           */
/* ------------------------------------------------------------------ */

export const api = {
  // health / admin
  health: () => request<{ status: string }>('GET', '/health'),
  seed: () => request<SeedResult>('POST', '/admin/seed'),
  workerTick: () => request<WorkerTickResult>('POST', '/admin/worker/tick'),
  watcherTick: () => request<WatcherTickResult>('POST', '/admin/watcher/tick'),

  // boards
  listBoards: () => request<Board[]>('GET', '/boards'),
  createBoard: (body: CreateBoardBody) =>
    request<Board>('POST', '/boards', body),
  getBoard: (boardId: number) =>
    request<Board>('GET', `/boards/${boardId}`),

  // projects + board templates
  listProjects: () => request<Project[]>('GET', '/projects'),
  getProject: (id: number) => request<Project>('GET', `/projects/${id}`),
  createProject: (body: CreateProjectBody) =>
    request<Project>('POST', '/projects', body),
  updateProject: (id: number, body: UpdateProjectBody) =>
    request<Project>('PATCH', `/projects/${id}`, body),
  archiveProject: (id: number) =>
    request<Project>('POST', `/projects/${id}/archive`),
  listBoardTemplates: () =>
    request<BoardTemplate[]>('GET', '/board-templates'),

  // models / permissions (Phase 5)
  listModels: (brain: string) =>
    request<ModelsForBrain>('GET', `/models?brain=${brain}`),
  listPermissionPresets: () =>
    request<{ default: string; presets: PermissionPreset[] }>('GET', '/permission-presets'),
  getAgentPermissions: (brain: string) =>
    request<PermissionProfile>('GET', `/agents/${brain}/permissions`),
  setAgentPermissions: (brain: string, body: { preset: string; allow?: string[]; deny?: string[] }) =>
    request<PermissionProfile>('PUT', `/agents/${brain}/permissions`, body),

  // subdivision (Phase 6)
  subdivide: (ticketId: number) =>
    request<SubdivisionProposal>('POST', `/tickets/${ticketId}/subdivide`),
  getSubdivision: (ticketId: number) =>
    request<SubdivisionProposal | null>('GET', `/tickets/${ticketId}/subdivision`),
  approveSubdivision: (proposalId: number) =>
    request<Ticket[]>('POST', `/subdivisions/${proposalId}/approve`),
  rejectSubdivision: (proposalId: number) =>
    request<SubdivisionProposal>('POST', `/subdivisions/${proposalId}/reject`),

  // memory / skills (Phase 7/8)
  memorySearch: (q: string, k = 6) =>
    request<MemoryHit[]>('GET', `/memory/search?q=${encodeURIComponent(q)}&k=${k}`),
  reindexMemory: () =>
    request<{ indexed_chunks: number }>('POST', '/memory/reindex'),
  listGeneratedSkills: () =>
    request<GeneratedSkill[]>('GET', '/skills/generated'),
  evolveSkill: (lesson: string, sourceConceptPath?: string) =>
    request<GeneratedSkill>('POST', '/skills/evolve', {
      lesson,
      source_concept_path: sourceConceptPath ?? null,
    }),
  acceptGeneratedSkill: (id: number) =>
    request<GeneratedSkill>('POST', `/skills/generated/${id}/accept`),
  rejectGeneratedSkill: (id: number) =>
    request<GeneratedSkill>('POST', `/skills/generated/${id}/reject`),

  // run log (Phase 5/§13)
  getRunLog: (runId: number, offset = 0) =>
    request<RunLog>('GET', `/runs/${runId}/log?offset=${offset}`),

  // status blocks
  listStatusBlocks: (boardId: number) =>
    request<StatusBlock[]>('GET', `/boards/${boardId}/status-blocks`),
  createStatusBlock: (boardId: number, body: CreateStatusBlockBody) =>
    request<StatusBlock>('POST', `/boards/${boardId}/status-blocks`, body),
  updateStatusBlock: (id: number, body: UpdateStatusBlockBody) =>
    request<StatusBlock>('PATCH', `/status-blocks/${id}`, body),
  deleteStatusBlock: (id: number) =>
    request<void>('DELETE', `/status-blocks/${id}`),

  // tickets
  listTickets: (boardId: number) =>
    request<Ticket[]>('GET', `/boards/${boardId}/tickets`),
  createTicket: (body: CreateTicketBody) =>
    request<Ticket>('POST', '/tickets', body),
  getTicket: (ticketId: number) =>
    request<TicketDetail>('GET', `/tickets/${ticketId}`),
  updateTicket: (ticketId: number, body: UpdateTicketBody) =>
    request<Ticket>('PATCH', `/tickets/${ticketId}`, body),

  // comments
  listComments: (ticketId: number) =>
    request<Comment[]>('GET', `/tickets/${ticketId}/comments`),
  createComment: (ticketId: number, body: CreateCommentBody) =>
    request<Comment>('POST', `/tickets/${ticketId}/comments`, body),

  // transition
  transition: (ticketId: number, body: TransitionBody) =>
    request<TransitionResult>('POST', `/tickets/${ticketId}/transition`, body),

  // navigator
  recommend: (ticketId: number, body: RecommendBody = {}) =>
    request<NavigatorDecision>(
      'POST',
      `/tickets/${ticketId}/navigator/recommend`,
      body,
    ),

  // runs
  createRun: (ticketId: number, body: CreateRunBody = {}) =>
    request<AgentRun>('POST', `/tickets/${ticketId}/runs`, body),
  getRun: (runId: number) =>
    request<AgentRunDetail>('GET', `/runs/${runId}`),
  cancelRun: (runId: number) =>
    request<AgentRun>('POST', `/runs/${runId}/cancel`),

  // queue
  getQueue: () => request<QueueItem[]>('GET', '/queue'),
  reorderQueue: (body: ReorderQueueBody) =>
    request<QueueItem[]>('PATCH', '/queue/reorder', body),
  cancelQueueItem: (queueItemId: number) =>
    request<QueueItem>('POST', `/queue/${queueItemId}/cancel`),

  // review
  review: (ticketId: number, body: ReviewBody) =>
    request<ReviewResult>('POST', `/tickets/${ticketId}/review`, body),

  // catalogs
  listPersonas: () => request<Persona[]>('GET', '/personas'),
  listSkills: () => request<Skill[]>('GET', '/skills'),

  // wiki sync
  listWikiJobs: () => request<WikiSyncJob[]>('GET', '/wiki-sync/jobs'),
  forkRaw: (ticketId: number, body: ForkRawBody = {}) =>
    request<ForkRawResult>(
      'POST',
      `/wiki-sync/tickets/${ticketId}/fork-raw`,
      body,
    ),
};
