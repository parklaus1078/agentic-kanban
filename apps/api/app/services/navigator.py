"""Navigator v1 — rule-first persona / agent / model / skill recommendation.

Classify the ticket into a persona via keyword scoring, then apply that persona's
default agent/model mapping. Skills are ranked by persona-compatibility + tag hits.
Manual override of persona/agent/model/skills is supported and recorded.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NavigatorDecision, Persona, Skill, Ticket

DEFAULT_PERSONA = "Full Stack Developer"

PERSONA_KEYWORDS: dict[str, list[str]] = {
    "PM": ["roadmap", "backlog", "prioritize", "stakeholder", "requirement", "scope", "milestone", "user story"],
    "QA(E2E)": ["e2e", "end-to-end", "user journey", "acceptance test", "regression", "smoke test"],
    "Marketer": ["marketing", "campaign", "seo", "landing page", "copywriting", "brand", "positioning", "ads", "growth"],
    "Accountant": ["invoice", "budget", "accounting", "tax", "reconcile", "ledger", "expense", "payroll"],
    "Strategist": ["strategy", "competitive", "market analysis", "business model", "pricing", "go-to-market", "okr"],
    "CS Manager": ["customer support", "helpdesk", "sla", "churn", "support playbook", "faq", "ticket response"],
    "Researcher": ["research", "survey", "literature", "whitepaper", "benchmark study", "investigate"],
    "CTO": ["architecture", "tech decision", "tradeoff", "scalability", "system design", "technical strategy", "adr", "rfc"],
    "Full Stack Developer": ["react", "fastapi", "frontend", "backend", "endpoint", "component", "crud",
                             "typescript", "python", "implement feature", "rest api", "ui"],
    "DevOps": ["docker", "kubernetes", "k8s", "ci/cd", "pipeline", "deploy", "terraform", "infrastructure",
               "compose", "helm", "nginx"],
    "Android Engineer": ["android", "kotlin", "jetpack", "gradle", "play store"],
    "iOS Engineer": ["ios", "swift", "swiftui", "xcode", "app store"],
    "AI Engineer": ["llm", "rag", "embedding", "agent", "prompt", "langchain", "vector", "fine-tune", "model integration"],
    "MLOps": ["mlops", "model serving", "training pipeline", "feature store", "mlflow", "model monitoring", "drift"],
    "Data Engineer": ["etl", "data pipeline", "warehouse", "airflow", "spark", "ingestion", "dbt", "schema design"],
    "QA(Unit test)": ["unit test", "pytest", "coverage", "mock", "test case", "assertion", "jest", "junit"],
    "SecOps": ["security", "vulnerability", "encryption", "secret", "pentest", "cve", "hardening", "owasp", "rbac", "auth"],
}


def _context(ticket: Ticket) -> str:
    parts = [ticket.title, ticket.description_md, ticket.acceptance_criteria_md]
    parts += [c.body_md for c in ticket.comments if c.is_digestible]
    return " ".join(p for p in parts if p).lower()


def _score_personas(context: str) -> list[tuple[str, int]]:
    scores = []
    for name, kws in PERSONA_KEYWORDS.items():
        s = sum(context.count(kw) for kw in kws)
        scores.append((name, s))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def _recommend_skills(db: Session, persona_name: str, context: str, limit: int = 3) -> list[str]:
    skills = db.scalars(select(Skill)).all()
    ranked = []
    for sk in skills:
        score = 0
        if persona_name in (sk.compatible_personas_json or []):
            score += 3
        for tag in sk.tags_json or []:
            if tag.lower() in context:
                score += 1
        if sk.name.replace("-", " ") in context:
            score += 2
        if score > 0:
            ranked.append((score, sk.name))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    chosen = [name for _, name in ranked[:limit]]
    if not chosen:
        # sensible default toolkit
        chosen = [s for s in ("product-spec", "test-driven-development") if s in {sk.name for sk in skills}][:limit]
    return chosen


def recommend(db: Session, ticket: Ticket, override: dict | None = None) -> NavigatorDecision:
    override = override or {}
    context = _context(ticket)
    scores = _score_personas(context)
    best_name, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0

    if best_score == 0:
        persona_name = DEFAULT_PERSONA
        confidence = 0.40
        reason = "No strong keyword signal; defaulted to Full Stack Developer (general engineering)."
    else:
        persona_name = best_name
        margin = best_score - second_score
        # Confidence = base 0.55, nudged up by absolute keyword hits (0.07 each) and by
        # the lead over the runner-up (0.05 each), clamped to [0.45, 0.95].
        confidence = round(min(0.95, max(0.45, 0.55 + 0.07 * best_score + 0.05 * margin)), 2)
        reason = (f"Persona '{persona_name}' scored highest ({best_score} keyword hits, "
                  f"margin {margin}). Mapped to its default agent/model.")

    if override.get("persona"):
        persona_name = override["persona"]
        reason = f"Manual override: persona set to '{persona_name}'. " + reason
        confidence = max(confidence, 0.99)

    persona = db.scalars(select(Persona).where(Persona.persona_name == persona_name)).first()
    if persona is None:  # override named an unknown persona; still honor it
        agent, model, family = "claude", "Claude CLI Sonnet 4.6", "engineering"
    else:
        agent, model, family = persona.default_agent, persona.default_model, persona.family

    if override.get("agent"):
        agent = override["agent"]
    if override.get("model"):
        model = override["model"]

    if override.get("skills") is not None:
        skills = override["skills"]
    else:
        skills = _recommend_skills(db, persona_name, context)

    # Alternatives: best candidate from the OTHER family + next in same family.
    persona_rows = {p.persona_name: p for p in db.scalars(select(Persona)).all()}
    alternatives: list[str] = []
    for name, sc in scores:
        if name == persona_name or name not in persona_rows:
            continue
        p = persona_rows[name]
        tag = "cross-family" if p.family != family else "same-family"
        alternatives.append(f"{name} ({p.default_agent} · {p.default_model}) [{tag}]" + (f", {sc} hits" if sc else ""))
        if len(alternatives) >= 3:
            break

    manual = bool(override.get("persona") or override.get("agent") or override.get("model") or override.get("skills") is not None)

    decision = NavigatorDecision(
        ticket_id=ticket.id, persona=persona_name, agent=agent, model=model,
        skills_json=skills, confidence=confidence, reason=reason,
        alternatives_json=alternatives, manual_override=manual,
    )
    db.add(decision)
    ticket.assignee_persona = persona_name
    db.flush()
    return decision
