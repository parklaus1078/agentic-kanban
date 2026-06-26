"""Pydantic v2 request/response schemas. Field names mirror docs/API_CONTRACT.md."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Status blocks / boards ----------
class StatusBlockOut(_ORM):
    id: int
    board_id: int
    name: str
    order_index: int
    color: str
    is_agent_digestible: bool
    digest_policy: str = "none"
    is_terminal: bool


class StatusBlockCreate(BaseModel):
    name: str
    color: str = "#9ca3af"
    is_agent_digestible: bool = False
    is_terminal: bool = False
    order_index: int | None = None


class StatusBlockUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    is_agent_digestible: bool | None = None
    order_index: int | None = None


class BoardOut(_ORM):
    id: int
    project_id: int | None = None
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    status_blocks: list[StatusBlockOut] = []


class BoardCreate(BaseModel):
    name: str
    description: str | None = None
    seed_default_statuses: bool = True


# ---------- Projects / board templates ----------
class BoardTemplateOut(_ORM):
    id: int
    name: str
    default_statuses_json: list = []
    default_digest_policy: str


class ProjectOut(_ORM):
    id: int
    slug: str
    title: str
    description: str | None = None
    board_template_id: int | None = None
    status: str
    board_id: int | None = None
    created_at: datetime


class ProjectCreate(BaseModel):
    title: str
    slug: str | None = None
    description: str | None = None
    board_template_id: int | None = None


class ProjectUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    description: str | None = None


# ---------- Tickets ----------
class TicketOut(_ORM):
    id: int
    board_id: int
    ticket_number: str
    title: str
    description_md: str
    acceptance_criteria_md: str
    status: str
    status_block_id: int
    assignee_persona: str | None = None
    priority: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None
    parent_ticket_id: int | None = None
    auto_complete_parent: bool = True


class SubdivisionProposalOut(_ORM):
    id: int
    parent_ticket_id: int
    proposed_children_json: list = []
    status: str
    created_by: str
    created_at: datetime


class TicketCreate(BaseModel):
    board_id: int
    title: str
    description_md: str = ""
    acceptance_criteria_md: str = ""
    assignee_persona: str | None = None
    priority: int = 3


class TicketUpdate(BaseModel):
    title: str | None = None
    description_md: str | None = None
    acceptance_criteria_md: str | None = None
    assignee_persona: str | None = None
    priority: int | None = None
    auto_complete_parent: bool | None = None


# ---------- Comments ----------
class CommentOut(_ORM):
    id: int
    ticket_id: int
    author_type: str
    author_name: str
    body_md: str
    body_latex_raw: str | None = None
    is_digestible: bool
    created_at: datetime


class CommentCreate(BaseModel):
    author_type: str = "human"
    author_name: str = ""
    body_md: str = ""
    body_latex_raw: str | None = None
    is_digestible: bool = True


# ---------- Status events / transitions ----------
class StatusEventOut(_ORM):
    id: int
    ticket_id: int
    from_status: str | None = None
    to_status: str
    actor: str
    reason_md: str | None = None
    wiki_raw_path: str | None = None
    created_at: datetime


class TransitionRequest(BaseModel):
    to_status: str
    actor: str = "Kay"
    reason_md: str | None = None


class TransitionResult(BaseModel):
    ticket: TicketOut
    status_event: StatusEventOut


# ---------- Personas / skills ----------
class PersonaOut(_ORM):
    id: int
    persona_name: str
    default_agent: str
    default_model: str
    family: str
    description: str
    risk_level: str
    is_active: bool


class SkillOut(_ORM):
    id: int
    name: str
    tags: list[str] = []
    compatible_personas: list[str] = []
    compatible_brains: list[str] = []
    description: str


# ---------- Navigator ----------
class NavigatorOverride(BaseModel):
    persona: str | None = None
    agent: str | None = None
    model: str | None = None
    skills: list[str] | None = None


class NavigatorRequest(BaseModel):
    override: NavigatorOverride | None = None


class NavigatorDecisionOut(_ORM):
    id: int
    ticket_id: int
    persona: str
    agent: str
    model: str
    skills: list[str] = []
    confidence: float
    reason: str
    alternatives: list[str] = []
    manual_override: bool
    created_at: datetime


# ---------- Artifacts / watcher events / runs ----------
class ArtifactOut(_ORM):
    id: int
    run_id: int
    path: str
    mime_type: str
    author_name: str
    summary: str
    checksum: str | None = None
    created_at: datetime


class WatcherEventOut(_ORM):
    id: int
    run_id: int
    event_type: str
    payload: dict = {}
    observed_at: datetime


class AgentRunOut(_ORM):
    id: int
    ticket_id: int
    run_number: int
    agent: str
    model: str
    persona: str
    prompt_md: str
    skills: list[str] = []
    plugins: list[str] = []
    output_path: str | None = None
    status: str
    process_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    created_at: datetime


class AgentRunDetailOut(AgentRunOut):
    artifacts: list[ArtifactOut] = []
    watcher_events: list[WatcherEventOut] = []


class RunCreate(BaseModel):
    use_navigator: bool = True
    persona: str | None = None
    agent: str | None = None
    model: str | None = None
    skills: list[str] | None = None


# ---------- Ticket detail ----------
class TicketDetailOut(TicketOut):
    comments: list[CommentOut] = []
    status_events: list[StatusEventOut] = []
    runs: list[AgentRunOut] = []
    navigator_decision: NavigatorDecisionOut | None = None


# ---------- Queue ----------
class QueueItemOut(_ORM):
    id: int
    ticket_id: int
    ticket_number: str
    ticket_title: str
    run_id: int | None = None
    order_index: int
    state: str
    cancel_requested: bool
    locked_by: str | None = None
    queued_at: datetime
    started_at: datetime | None = None


class QueueReorderRequest(BaseModel):
    ordered_ids: list[int]


# ---------- Review ----------
class ReviewRequest(BaseModel):
    satisfied: bool
    comment_md: str | None = None
    actor: str = "Kay"


class ReviewResult(BaseModel):
    ticket: TicketOut
    rerun: AgentRunOut | None = None


# ---------- Wiki ----------
class WikiSyncJobOut(_ORM):
    id: int
    ticket_id: int
    raw_path: str
    ingest_status: str
    audit_status: str
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class ForkRawRequest(BaseModel):
    note_md: str | None = None


class ForkRawResult(BaseModel):
    raw_path: str


# ---------- Admin / misc ----------
class SeedResult(BaseModel):
    board: BoardOut
    personas: int
    skills: int


class TickResult(BaseModel):
    processed: list[int] = Field(default_factory=list)


class WatchTickResult(BaseModel):
    detected: list[int] = Field(default_factory=list)
