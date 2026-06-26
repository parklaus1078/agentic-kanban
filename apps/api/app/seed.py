"""Seed data: default statuses, board template, 17 personas, skill catalog.

`seed_all` is idempotent — safe to call on every startup or via POST /admin/seed.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import transitions as T
from .models import Board, BoardTemplate, Persona, Project, Skill, StatusBlock, Ticket

DEFAULT_STATUSES = [
    # (name, color, is_agent_digestible, is_terminal)
    (T.TRIAGE, "#a77cff", False, False),
    (T.TODO, "#93c5fd", False, False),
    (T.IN_PROGRESS, "#ffd166", True, False),
    (T.BLOCKED, "#ff6b7a", False, False),
    (T.REVIEWING, "#c4b5fd", False, False),
    (T.COMPLETED, "#5ee38f", False, True),
    (T.CANCELED, "#9ca3af", False, True),
]

CODEX_MODEL = "Codex CLI gpt 5.5"
CLAUDE_OPUS = "Claude CLI Opus 4.8"
CLAUDE_SONNET = "Claude CLI Sonnet 4.6"

# (persona_name, default_agent, default_model, family, risk_level, description)
PERSONAS = [
    # Codex CLI gpt 5.5 group (business)
    ("PM", "codex", CODEX_MODEL, "business", "low", "Product management: scoping, acceptance criteria, prioritization."),
    ("QA(E2E)", "codex", CODEX_MODEL, "business", "low", "End-to-end product QA from a user/journey perspective."),
    ("Marketer", "codex", CODEX_MODEL, "business", "low", "Positioning, messaging, go-to-market and campaigns."),
    ("Accountant", "codex", CODEX_MODEL, "business", "low", "Bookkeeping, financial modeling and reconciliation."),
    ("Strategist", "codex", CODEX_MODEL, "business", "low", "Business strategy, competitive analysis, roadmap framing."),
    ("CS Manager", "codex", CODEX_MODEL, "business", "low", "Customer support operations and playbooks."),
    ("Researcher", "codex", CODEX_MODEL, "business", "low", "Market/technical research and synthesis."),
    # Claude CLI group (engineering)
    ("CTO", "claude", CLAUDE_OPUS, "engineering", "medium", "Technical decisions, architecture, risk and tradeoffs."),
    ("Full Stack Developer", "claude", CLAUDE_SONNET, "engineering", "low", "React + FastAPI feature implementation and tests."),
    ("DevOps", "claude", CLAUDE_SONNET, "engineering", "medium", "CI/CD, Docker, Kubernetes, infrastructure operations."),
    ("Android Engineer", "claude", CLAUDE_SONNET, "engineering", "low", "Android/Kotlin app development."),
    ("iOS Engineer", "claude", CLAUDE_SONNET, "engineering", "low", "iOS/Swift app development."),
    ("AI Engineer", "claude", CLAUDE_OPUS, "engineering", "medium", "LLM apps, RAG, agents, model integration."),
    ("MLOps", "claude", CLAUDE_SONNET, "engineering", "medium", "ML pipelines, serving, monitoring and retraining."),
    ("Data Engineer", "claude", CLAUDE_SONNET, "engineering", "low", "Data pipelines, schemas, warehousing and ETL."),
    ("QA(Unit test)", "claude", CLAUDE_SONNET, "engineering", "low", "Unit/integration test design and coverage."),
    ("SecOps", "claude", CLAUDE_OPUS, "engineering", "high", "Security review, hardening and incident response."),
]

# (name, tags, compatible_personas, compatible_brains, description)
SKILLS = [
    ("test-driven-development", ["testing", "quality"],
     ["Full Stack Developer", "QA(Unit test)", "AI Engineer", "Data Engineer", "Android Engineer", "iOS Engineer"],
     ["claude", "codex"], "Write tests first, then implement until green."),
    ("github-pr-workflow", ["vcs", "collaboration"],
     ["Full Stack Developer", "DevOps", "CTO"], ["claude", "codex"], "Branch, commit, open and review PRs."),
    ("fastapi-backend", ["backend", "python", "api"],
     ["Full Stack Developer", "AI Engineer", "Data Engineer"], ["claude"], "Build FastAPI services and endpoints."),
    ("react-frontend", ["frontend", "typescript", "ui"],
     ["Full Stack Developer"], ["claude"], "Build React + TypeScript UIs."),
    ("docker-compose", ["infra", "containers"],
     ["DevOps", "Full Stack Developer"], ["claude"], "Author and operate Docker Compose stacks."),
    ("kubernetes-ops", ["infra", "k8s"],
     ["DevOps", "MLOps", "SecOps"], ["claude"], "Deploy and operate Kubernetes workloads."),
    ("postgres-schema-design", ["database", "sql"],
     ["Data Engineer", "Full Stack Developer"], ["claude"], "Design relational schemas and migrations."),
    ("security-review", ["security", "audit"],
     ["SecOps", "CTO"], ["claude", "codex"], "Threat-model and review code/infra for risk."),
    ("data-pipeline", ["data", "etl"],
     ["Data Engineer", "MLOps"], ["claude"], "Design ETL/ELT pipelines."),
    ("mobile-release", ["mobile"],
     ["Android Engineer", "iOS Engineer"], ["claude"], "Build and ship mobile releases."),
    ("e2e-testing", ["testing", "qa"],
     ["QA(E2E)", "QA(Unit test)"], ["codex", "claude"], "Author end-to-end test journeys."),
    ("market-research", ["marketing", "research"],
     ["Marketer", "Researcher", "Strategist"], ["codex"], "Research markets, competitors and trends."),
    ("product-spec", ["product", "planning"],
     ["PM", "Strategist"], ["codex"], "Write product specs and acceptance criteria."),
    ("financial-modeling", ["finance"],
     ["Accountant"], ["codex"], "Build budgets, forecasts and reconciliations."),
    ("customer-support-playbook", ["support"],
     ["CS Manager"], ["codex"], "Design customer support playbooks and responses."),
]


def seed_statuses(db: Session, board: Board) -> None:
    existing = {sb.name for sb in board.status_blocks}
    for i, (name, color, digest, terminal) in enumerate(DEFAULT_STATUSES):
        if name in existing:
            continue
        db.add(StatusBlock(
            board_id=board.id, name=name, order_index=i, color=color,
            is_agent_digestible=digest, is_terminal=terminal,
            digest_policy=(T.DIGEST_AGENT_EXECUTE if name == T.IN_PROGRESS else T.DIGEST_NONE),
        ))
    db.flush()


def seed_personas(db: Session) -> int:
    existing = {p.persona_name for p in db.scalars(select(Persona)).all()}
    added = 0
    for name, agent, model, family, risk, desc in PERSONAS:
        if name in existing:
            continue
        db.add(Persona(persona_name=name, default_agent=agent, default_model=model,
                       family=family, risk_level=risk, description=desc, is_active=True))
        added += 1
    db.flush()
    return added


def seed_skills(db: Session) -> int:
    existing = {s.name for s in db.scalars(select(Skill)).all()}
    added = 0
    for name, tags, personas, brains, desc in SKILLS:
        if name in existing:
            continue
        db.add(Skill(name=name, tags_json=tags, compatible_personas_json=personas,
                     compatible_brains_json=brains, description=desc))
        added += 1
    db.flush()
    return added


def seed_template(db: Session) -> None:
    if db.scalar(select(BoardTemplate).where(BoardTemplate.name == "Standard Kanban")):
        return
    db.add(BoardTemplate(
        name="Standard Kanban",
        default_statuses_json=[s[0] for s in DEFAULT_STATUSES],
        default_digest_policy="manual",
    ))
    db.flush()


def get_or_create_default_board(db: Session) -> Board:
    board = db.scalars(select(Board).order_by(Board.id)).first()
    if board is None:
        board = Board(name="Default Board", description="Agent System v2 default Kanban board")
        db.add(board)
        db.flush()
        seed_statuses(db, board)
    return board


def get_or_create_default_project(db: Session, board: Board) -> Project:
    project = db.scalars(select(Project).order_by(Project.id)).first()
    if project is None:
        project = Project(slug="default", title="Default Project",
                          description="Agent System v2 default project")
        db.add(project)
        db.flush()
    if board.project_id is None:
        board.project_id = project.id
    return project


def next_ticket_number(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(Ticket)) or 0
    return f"ASV2-{count + 1:04d}"


def seed_all(db: Session) -> tuple[Board, int, int]:
    seed_template(db)
    n_personas = seed_personas(db)
    n_skills = seed_skills(db)
    board = get_or_create_default_board(db)
    get_or_create_default_project(db, board)
    db.commit()
    db.refresh(board)
    return board, n_personas, n_skills
