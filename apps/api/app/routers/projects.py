"""Project CRUD (above boards) + board templates. Phase 2.

A project provisions its first board (seeded from the chosen template's statuses,
incl. the agent_execute digest policy) on creation. Archive is a soft delete.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, seed
from ..db import get_db
from ..models import Board, BoardTemplate, Project

router = APIRouter(tags=["projects"])


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "project"


def _unique_slug(db: Session, base: str) -> str:
    slug, n = base, 2
    while db.scalar(select(Project).where(Project.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def _get_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return p


@router.get("/board-templates", response_model=list[schemas.BoardTemplateOut])
def list_board_templates(db: Session = Depends(get_db)):
    return db.scalars(select(BoardTemplate).order_by(BoardTemplate.id)).all()


@router.get("/projects", response_model=list[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.id)).all()


@router.post("/projects", response_model=schemas.ProjectOut, status_code=201)
def create_project(body: schemas.ProjectCreate, db: Session = Depends(get_db)):
    if body.board_template_id is not None and db.get(BoardTemplate, body.board_template_id) is None:
        raise HTTPException(404, f"Board template {body.board_template_id} not found")
    slug = _unique_slug(db, _slugify(body.slug or body.title))
    project = Project(slug=slug, title=body.title, description=body.description,
                      board_template_id=body.board_template_id)
    db.add(project)
    db.flush()
    board = Board(project_id=project.id, name=body.title, description=f"Board for {body.title}")
    db.add(board)
    db.flush()
    seed.seed_statuses(db, board)  # seeds default statuses incl. In Progress=agent_execute
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _get_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: int, body: schemas.ProjectUpdate, db: Session = Depends(get_db)):
    p = _get_project(db, project_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("slug"):
        data["slug"] = _unique_slug(db, _slugify(data["slug"]))
    for field, value in data.items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return p


@router.post("/projects/{project_id}/archive", response_model=schemas.ProjectOut)
def archive_project(project_id: int, db: Session = Depends(get_db)):
    p = _get_project(db, project_id)
    p.status = "archived"
    db.commit()
    db.refresh(p)
    return p
