"""Phase 8 — self-evolution: lessons → skill proposals (spec §16.1).

When a recurring lesson crosses a threshold, the system proposes a skill. It first
looks for a similar EXISTING skill/plugin across three sources — (1) the installed
catalog, (2) a plugin market registry, (3) Web Search — and if one matches, proposes
``install_existing`` (Kay accepts → install via CLI). Otherwise it proposes ``new``
(Kay accepts → generate a superpowers-compatible skill). Activation is Kay-gated.

The installed-catalog search is real and unit-tested; the market/Web-Search sources
are guarded hooks that return nothing offline (wired for real mode).
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GeneratedSkill, Skill


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")[:60] or "skill"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _search_installed(db: Session, lesson: str, limit: int = 3) -> list[tuple[int, str, str]]:
    toks = _tokens(lesson)
    out: list[tuple[int, str, str]] = []
    for s in db.scalars(select(Skill)).all():
        hay = _tokens(f"{s.name} {s.description} {' '.join(s.tags_json or [])}")
        overlap = len(toks & hay)
        if overlap:
            out.append((overlap, s.name, s.description))
    out.sort(key=lambda x: -x[0])
    return out[:limit]


def _search_market(lesson: str) -> list[tuple[int, str, str]]:  # pragma: no cover - real mode
    """Plugin market/registry lookup. Offline: empty. Wired for real mode."""
    return []


def _search_web(lesson: str) -> list[tuple[int, str, str]]:  # pragma: no cover - real mode
    """Web Search for an existing plugin. Offline: empty. Wired for real mode."""
    return []


def find_similar(db: Session, lesson: str, limit: int = 3) -> list[dict]:
    """Merge the three sources (installed + market + web), best overlap first."""
    merged = _search_installed(db, lesson, limit) + _search_market(lesson) + _search_web(lesson)
    merged.sort(key=lambda x: -x[0])
    return [{"name": n, "description": d, "score": sc} for sc, n, d in merged[:limit]]


def propose_skill(db: Session, lesson: str, source_concept_path: str | None = None) -> GeneratedSkill:
    similar = find_similar(db, lesson)
    if similar:
        top = similar[0]
        gs = GeneratedSkill(
            slug=_slug(top["name"]), kind="install_existing", suggested_ref=top["name"],
            body_md=f"Existing skill **{top['name']}** matches this lesson:\n\n{top['description']}",
            source_concept_path=source_concept_path, status="proposed",
        )
    else:
        gs = GeneratedSkill(
            slug=_slug(lesson[:40]), kind="new", suggested_ref=None,
            body_md=f"# Generated skill (draft)\n\nLesson learned:\n\n{lesson}\n",
            source_concept_path=source_concept_path, status="proposed",
        )
    db.add(gs)
    db.flush()
    return gs


def accept(db: Session, gs: GeneratedSkill, approved_by: str = "Kay") -> GeneratedSkill:
    # Real mode: install_existing → `claude plugin install` / `codex` equivalent;
    # new → write a superpowers-compatible skill file. Guarded; activation is the gate.
    gs.status = "active"
    gs.approved_by = approved_by
    db.flush()
    return gs


def reject(db: Session, gs: GeneratedSkill) -> GeneratedSkill:
    gs.status = "retired"
    db.flush()
    return gs
