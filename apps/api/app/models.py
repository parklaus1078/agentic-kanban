"""SQLAlchemy ORM models for Agent System v2.

Portable types only (JSON works on both SQLite and Postgres). Timestamps are
stored as naive UTC; serialization adds the trailing 'Z'.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class Board(Base):
    __tablename__ = "boards"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), default=None
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    project: Mapped["Project | None"] = relationship(back_populates="boards")
    status_blocks: Mapped[list["StatusBlock"]] = relationship(
        back_populates="board", cascade="all, delete-orphan", order_by="StatusBlock.order_index"
    )
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="board", cascade="all, delete-orphan")


class BoardTemplate(Base):
    __tablename__ = "board_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    default_statuses_json: Mapped[list] = mapped_column(JSON, default=list)
    default_digest_policy: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Project(Base):
    """A project sits above boards: slug/title, an optional source template, and a
    soft-delete (archive) status. Creating a project provisions its first board."""
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    board_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("board_templates.id"), default=None
    )
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    boards: Mapped[list["Board"]] = relationship(
        back_populates="project", order_by="Board.id"
    )

    @property
    def board_id(self) -> int | None:
        return self.boards[0].id if self.boards else None


class GeneratedSkill(Base):
    """Phase 8 — self-evolution (§16.1). A recurring lesson becomes a skill proposal:
    if a similar installed/market skill exists → ``install_existing`` (Kay accepts →
    install via CLI); else ``new`` (Kay accepts → generate). Activation is gated."""
    __tablename__ = "generated_skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120))
    source_concept_path: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[str] = mapped_column(String(20), default="new")  # install_existing | new
    suggested_ref: Mapped[str | None] = mapped_column(String(200), default=None)  # existing skill/plugin name
    body_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed|active|retired
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    approved_by: Mapped[str | None] = mapped_column(String(40), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class WikiEmbedding(Base):
    """RAG index over LLM Wiki *synthesized* pages (Phase 7, §15). Embeddings stored
    as JSON for portability (SQLite + Postgres); pgvector is the production optimization.
    Raw sources are never embedded — only the wiki/ pages (cheap-read rule)."""
    __tablename__ = "wiki_embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    wiki_path: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    chunk: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[list] = mapped_column(JSON, default=list)
    page_type: Mapped[str | None] = mapped_column(String(20), default=None)
    outcome: Mapped[str | None] = mapped_column(String(20), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class SubdivisionProposal(Base):
    """A Navigator-routed proposal to split a ticket into child tickets (Phase 6, §8).
    Kay approves → children are created in Todo with parent_ticket_id set."""
    __tablename__ = "subdivision_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    proposed_children_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed|approved|rejected
    created_by: Mapped[str] = mapped_column(String(40), default="Navigator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AgentPermissionProfile(Base):
    """Per-brain permission scope (Phase 5, §11). Stores the chosen preset; applied to
    the CLI settings/config files at session launch (real mode)."""
    __tablename__ = "agent_permission_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain: Mapped[str] = mapped_column(String(20), unique=True)  # claude | codex
    preset: Mapped[str] = mapped_column(String(20), default="auto")
    allow_json: Mapped[list] = mapped_column(JSON, default=list)
    deny_json: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ScheduledJob(Base):
    """Durable schedule store so cron-like jobs (rate-limit resume, snapshots) can be
    re-armed after a power cut wipes the OS crontab. Phase 3."""
    __tablename__ = "scheduled_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # ratelimit_resume | snapshot | ingest | ...
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), default=None
    )
    fire_at: Mapped[datetime] = mapped_column(DateTime)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|done|canceled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class StatusBlock(Base):
    __tablename__ = "status_blocks"
    __table_args__ = (UniqueConstraint("board_id", "name", name="uq_statusblock_board_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(20), default="#9ca3af")
    is_agent_digestible: Mapped[bool] = mapped_column(Boolean, default=False)
    # What the system does when a ticket ENTERS this block: "none" | "agent_execute".
    digest_policy: Mapped[str] = mapped_column(String(20), default="none")
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)

    board: Mapped[Board] = relationship(back_populates="status_blocks")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"))
    ticket_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(400))
    description_md: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria_md: Mapped[str] = mapped_column(Text, default="")
    status_block_id: Mapped[int] = mapped_column(ForeignKey("status_blocks.id"))
    assignee_persona: Mapped[str | None] = mapped_column(String(100), default=None)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # Phase 6 — recursive subdivision (parent epic → child tickets).
    parent_ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), default=None
    )
    auto_complete_parent: Mapped[bool] = mapped_column(Boolean, default=True)

    board: Mapped[Board] = relationship(back_populates="tickets")
    status_block: Mapped[StatusBlock] = relationship()
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    status_events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="StatusEvent.created_at"
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="AgentRun.run_number"
    )
    navigator_decisions: Mapped[list["NavigatorDecision"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="NavigatorDecision.created_at"
    )
    parent: Mapped["Ticket | None"] = relationship(
        "Ticket", remote_side="Ticket.id", back_populates="children"
    )
    children: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="parent")

    @property
    def status(self) -> str:
        return self.status_block.name if self.status_block else ""


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    author_type: Mapped[str] = mapped_column(String(40), default="human")
    author_name: Mapped[str] = mapped_column(String(120), default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    body_latex_raw: Mapped[str | None] = mapped_column(Text, default=None)
    is_digestible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="comments")


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(100), default=None)
    to_status: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(120), default="system")
    reason_md: Mapped[str | None] = mapped_column(Text, default=None)
    wiki_raw_path: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="status_events")


class Persona(Base):
    __tablename__ = "personas"
    id: Mapped[int] = mapped_column(primary_key=True)
    persona_name: Mapped[str] = mapped_column(String(100), unique=True)
    default_agent: Mapped[str] = mapped_column(String(20))  # codex | claude
    default_model: Mapped[str] = mapped_column(String(80))
    family: Mapped[str] = mapped_column(String(40))  # business | engineering
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    compatible_personas_json: Mapped[list] = mapped_column(JSON, default=list)
    compatible_brains_json: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")

    @property
    def tags(self) -> list:
        return self.tags_json or []

    @property
    def compatible_personas(self) -> list:
        return self.compatible_personas_json or []

    @property
    def compatible_brains(self) -> list:
        return self.compatible_brains_json or []


class NavigatorDecision(Base):
    __tablename__ = "navigator_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    persona: Mapped[str] = mapped_column(String(100))
    agent: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    skills_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    alternatives_json: Mapped[list] = mapped_column(JSON, default=list)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    task_kind: Mapped[str] = mapped_column(String(20), default="execute")  # execute | subdivide
    rag_context_refs: Mapped[list] = mapped_column(JSON, default=list)  # wiki pages injected (§15)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="navigator_decisions")

    @property
    def skills(self) -> list:
        return self.skills_json or []

    @property
    def alternatives(self) -> list:
        return self.alternatives_json or []


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    run_number: Mapped[int] = mapped_column(Integer, default=1)
    agent: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    persona: Mapped[str] = mapped_column(String(100))
    prompt_md: Mapped[str] = mapped_column(Text, default="")
    skills_json: Mapped[list] = mapped_column(JSON, default=list)
    plugins_json: Mapped[list] = mapped_column(JSON, default=list)
    output_path: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    process_id: Mapped[str | None] = mapped_column(String(80), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    # Phase 5 — interactive tmux execution + live log + fallback/rate-limit.
    log_path: Mapped[str | None] = mapped_column(Text, default=None)
    tmux_window: Mapped[str | None] = mapped_column(String(80), default=None)
    cli_session_id: Mapped[str | None] = mapped_column(String(120), default=None)
    rate_limit_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="runs")
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Artifact.created_at"
    )
    watcher_events: Mapped[list["WatcherEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="WatcherEvent.observed_at"
    )

    @property
    def skills(self) -> list:
        return self.skills_json or []

    @property
    def plugins(self) -> list:
        return self.plugins_json or []


class QueueItem(Base):
    __tablename__ = "queue_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), default=None)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|canceled
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_by: Mapped[str | None] = mapped_column(String(80), default=None)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    ticket: Mapped["Ticket"] = relationship()

    @property
    def ticket_number(self) -> str:
        return self.ticket.ticket_number if self.ticket else ""

    @property
    def ticket_title(self) -> str:
        return self.ticket.title if self.ticket else ""


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(80), default="application/octet-stream")
    author_name: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    checksum: Mapped[str | None] = mapped_column(String(80), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="artifacts")


class WatcherEvent(Base):
    __tablename__ = "watcher_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(60))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="watcher_events")

    @property
    def payload(self) -> dict:
        return self.payload_json or {}


class WikiSyncJob(Base):
    __tablename__ = "wiki_sync_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    raw_path: Mapped[str] = mapped_column(Text)
    ingest_status: Mapped[str] = mapped_column(String(20), default="pending")
    audit_status: Mapped[str] = mapped_column(String(20), default="pending")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
