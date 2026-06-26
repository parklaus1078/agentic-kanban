"""System endpoints: durability (Phase 3) + model registry & permissions (Phase 5)."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import model_registry
from ..config import settings
from ..db import get_db
from ..models import AgentPermissionProfile, GeneratedSkill, ScheduledJob
from ..services import durability, permissions, rag, skills_evolve

router = APIRouter(tags=["system"])


@router.get("/system/snapshots")
def list_snapshots() -> list[str]:
    return durability.list_snapshots()


@router.post("/system/snapshots")
def create_snapshot() -> dict:
    stamp = (datetime.utcnow() + timedelta(hours=settings.tz_offset_hours)).strftime(
        "%Y%m%d-%H%M%S"
    )
    path = durability.create_snapshot(stamp)
    durability.prune_snapshots()
    return {"created": path, "snapshots": durability.list_snapshots()}


# ---------- Phase 5: model registry (SSOT) + agent permissions ----------
@router.get("/models")
def list_models(brain: str | None = None) -> dict:
    if brain:
        return {"brain": brain, "default": model_registry.default_model(brain),
                "models": model_registry.list_models(brain)}
    return model_registry.MODELS


@router.get("/permission-presets")
def list_permission_presets() -> dict:
    return {"default": permissions.DEFAULT_PRESET, "presets": permissions.presets()}


def _profile_view(brain: str, prof: AgentPermissionProfile | None) -> dict:
    preset = prof.preset if prof else permissions.DEFAULT_PRESET
    return {
        "brain": brain,
        "preset": preset,
        "allow": (prof.allow_json if prof else []),
        "deny": (prof.deny_json if prof else []),
        "flags": permissions.flags_for(brain, preset),
    }


@router.get("/agents/{brain}/permissions")
def get_agent_permissions(brain: str, db: Session = Depends(get_db)) -> dict:
    prof = db.scalars(
        select(AgentPermissionProfile).where(AgentPermissionProfile.brain == brain)
    ).first()
    return _profile_view(brain, prof)


class PermissionUpdate(BaseModel):
    preset: str = permissions.DEFAULT_PRESET
    allow: list[str] = []
    deny: list[str] = []


@router.put("/agents/{brain}/permissions")
def set_agent_permissions(brain: str, body: PermissionUpdate, db: Session = Depends(get_db)) -> dict:
    prof = db.scalars(
        select(AgentPermissionProfile).where(AgentPermissionProfile.brain == brain)
    ).first()
    if prof is None:
        prof = AgentPermissionProfile(brain=brain)
        db.add(prof)
    prof.preset = body.preset
    prof.allow_json = body.allow
    prof.deny_json = body.deny
    db.commit()
    db.refresh(prof)
    return _profile_view(brain, prof)


# ---------- Phase 8: self-evolution (generated skills) ----------
def _gs_view(gs: GeneratedSkill) -> dict:
    return {"id": gs.id, "slug": gs.slug, "kind": gs.kind, "suggested_ref": gs.suggested_ref,
            "status": gs.status, "risk_level": gs.risk_level, "approved_by": gs.approved_by,
            "source_concept_path": gs.source_concept_path, "body_md": gs.body_md}


class EvolveRequest(BaseModel):
    lesson: str
    source_concept_path: str | None = None


@router.get("/skills/generated")
def list_generated_skills(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(GeneratedSkill).order_by(GeneratedSkill.id.desc())).all()
    return [_gs_view(g) for g in rows]


@router.post("/skills/evolve")
def evolve_skill(body: EvolveRequest, db: Session = Depends(get_db)) -> dict:
    gs = skills_evolve.propose_skill(db, body.lesson, body.source_concept_path)
    db.commit()
    db.refresh(gs)
    return _gs_view(gs)


@router.post("/skills/generated/{gs_id}/accept")
def accept_generated_skill(gs_id: int, db: Session = Depends(get_db)) -> dict:
    gs = db.get(GeneratedSkill, gs_id)
    if gs is None:
        raise HTTPException(404, f"Generated skill {gs_id} not found")
    skills_evolve.accept(db, gs)
    db.commit()
    db.refresh(gs)
    return _gs_view(gs)


@router.post("/skills/generated/{gs_id}/reject")
def reject_generated_skill(gs_id: int, db: Session = Depends(get_db)) -> dict:
    gs = db.get(GeneratedSkill, gs_id)
    if gs is None:
        raise HTTPException(404, f"Generated skill {gs_id} not found")
    skills_evolve.reject(db, gs)
    db.commit()
    db.refresh(gs)
    return _gs_view(gs)


# ---------- Phase 7: RAG memory ----------
@router.get("/memory/search")
def memory_search(q: str, k: int = 4, db: Session = Depends(get_db)) -> list[dict]:
    return rag.search(db, q, k)


@router.post("/memory/reindex")
def memory_reindex(db: Session = Depends(get_db)) -> dict:
    return {"indexed_chunks": rag.reindex_from_wiki(db)}


@router.get("/scheduled-jobs")
def list_scheduled_jobs(db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(ScheduledJob).order_by(ScheduledJob.fire_at)).all()
    return [
        {
            "id": j.id,
            "kind": j.kind,
            "run_id": j.run_id,
            "fire_at": j.fire_at.isoformat(),
            "status": j.status,
            "payload": j.payload_json,
        }
        for j in jobs
    ]
