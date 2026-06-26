"""Persona + skill catalog (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import Persona, Skill

router = APIRouter(tags=["catalog"])


@router.get("/personas", response_model=list[schemas.PersonaOut])
def list_personas(db: Session = Depends(get_db)):
    return db.scalars(select(Persona).order_by(Persona.id)).all()


@router.get("/skills", response_model=list[schemas.SkillOut])
def list_skills(db: Session = Depends(get_db)):
    return db.scalars(select(Skill).order_by(Skill.id)).all()
