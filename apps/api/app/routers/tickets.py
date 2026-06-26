"""Ticket CRUD + comments + transition + navigator + run creation + review."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, seed, transitions as T
from ..db import get_db
from ..models import Board, Comment, Persona, StatusBlock, SubdivisionProposal, Ticket
from ..services import lifecycle, navigator, review, runs, subdivision

router = APIRouter(tags=["tickets"])


def _get_ticket(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return ticket


def _detail(ticket: Ticket) -> schemas.TicketDetailOut:
    detail = schemas.TicketDetailOut.model_validate(ticket)
    if ticket.navigator_decisions:
        detail.navigator_decision = schemas.NavigatorDecisionOut.model_validate(ticket.navigator_decisions[-1])
    return detail


@router.get("/boards/{board_id}/tickets", response_model=list[schemas.TicketOut])
def list_board_tickets(board_id: int, db: Session = Depends(get_db)):
    if db.get(Board, board_id) is None:
        raise HTTPException(404, f"Board {board_id} not found")
    return db.scalars(select(Ticket).where(Ticket.board_id == board_id).order_by(Ticket.id)).all()


@router.post("/tickets", response_model=schemas.TicketOut, status_code=201)
def create_ticket(body: schemas.TicketCreate, db: Session = Depends(get_db)):
    board = db.get(Board, body.board_id)
    if board is None:
        raise HTTPException(404, f"Board {body.board_id} not found")
    triage = lifecycle.get_status_block(db, board.id, "Triage/Ready")
    if triage is None:
        raise HTTPException(409, "Board has no 'Triage/Ready' status block")
    ticket = Ticket(
        board_id=board.id, ticket_number=seed.next_ticket_number(db), title=body.title,
        description_md=body.description_md, acceptance_criteria_md=body.acceptance_criteria_md,
        status_block_id=triage.id, assignee_persona=body.assignee_persona, priority=body.priority,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/tickets/{ticket_id}", response_model=schemas.TicketDetailOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    return _detail(_get_ticket(db, ticket_id))


@router.patch("/tickets/{ticket_id}", response_model=schemas.TicketOut)
def update_ticket(ticket_id: int, body: schemas.TicketUpdate, db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/tickets/{ticket_id}/comments", response_model=list[schemas.CommentOut])
def list_comments(ticket_id: int, db: Session = Depends(get_db)):
    _get_ticket(db, ticket_id)
    return db.scalars(select(Comment).where(Comment.ticket_id == ticket_id).order_by(Comment.created_at)).all()


@router.post("/tickets/{ticket_id}/comments", response_model=schemas.CommentOut, status_code=201)
def add_comment(ticket_id: int, body: schemas.CommentCreate, db: Session = Depends(get_db)):
    _get_ticket(db, ticket_id)
    comment = Comment(ticket_id=ticket_id, **body.model_dump())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def _has_active_run(ticket: Ticket) -> bool:
    return any(r.status in ("queued", "running") for r in ticket.runs)


def _maybe_auto_dispatch(db: Session, ticket: Ticket) -> None:
    """Entering an `agent_execute` status is the trigger: auto-run the Navigator and
    enqueue a run (drag = execute). Guarded so re-entry or an already-active run does
    not create duplicates. The worker drives execution off the queue from here."""
    block = db.get(StatusBlock, ticket.status_block_id)
    if block is None or block.digest_policy != T.DIGEST_AGENT_EXECUTE:
        return
    if _has_active_run(ticket):
        return
    decision = navigator.recommend(db, ticket, None)
    runs.create_run(db, ticket, decision.persona, decision.agent,
                    decision.model, decision.skills_json)


@router.post("/tickets/{ticket_id}/transition", response_model=schemas.TransitionResult)
def transition(ticket_id: int, body: schemas.TransitionRequest, db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    try:
        event = lifecycle.transition_ticket(db, ticket, body.to_status, actor=body.actor, reason_md=body.reason_md)
    except lifecycle.TransitionError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _maybe_auto_dispatch(db, ticket)
    db.commit()
    db.refresh(ticket)
    db.refresh(event)
    return schemas.TransitionResult(
        ticket=schemas.TicketOut.model_validate(ticket),
        status_event=schemas.StatusEventOut.model_validate(event),
    )


@router.post("/tickets/{ticket_id}/navigator/recommend", response_model=schemas.NavigatorDecisionOut)
def navigator_recommend(ticket_id: int, body: schemas.NavigatorRequest, db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    override = body.override.model_dump(exclude_none=True) if body.override else None
    decision = navigator.recommend(db, ticket, override)
    db.commit()
    db.refresh(decision)
    return decision


@router.post("/tickets/{ticket_id}/runs", response_model=schemas.AgentRunOut, status_code=201)
def create_run(ticket_id: int, body: schemas.RunCreate, db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    if body.use_navigator or not body.persona:
        override = {k: v for k, v in {"persona": body.persona, "agent": body.agent,
                                      "model": body.model, "skills": body.skills}.items() if v is not None}
        decision = navigator.recommend(db, ticket, override or None)
        persona, agent, model, skills = decision.persona, decision.agent, decision.model, decision.skills_json
    else:
        persona = body.persona
        prow = db.scalars(select(Persona).where(Persona.persona_name == persona)).first()
        agent = body.agent or (prow.default_agent if prow else "claude")
        model = body.model or (prow.default_model if prow else "Claude CLI Sonnet 4.6")
        skills = body.skills or []
    run = runs.create_run(db, ticket, persona, agent, model, skills)
    db.commit()
    db.refresh(run)
    return run


@router.post("/tickets/{ticket_id}/orchestrate")
def orchestrate(ticket_id: int, db: Session = Depends(get_db)):
    """Drive one ticket through the LangGraph lifecycle (navigate→dispatch→watch).
    Lazy import keeps the app bootable even before langgraph is installed."""
    _get_ticket(db, ticket_id)
    from ..services import orchestrator

    state = orchestrator.run_ticket(ticket_id)
    db.expire_all()
    ticket = _get_ticket(db, ticket_id)
    return {"ticket_id": ticket_id, "status": ticket.status, "run_id": state.get("run_id")}


@router.post("/tickets/{ticket_id}/subdivide", response_model=schemas.SubdivisionProposalOut)
def subdivide(ticket_id: int, db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    proposal = subdivision.propose(db, ticket)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.get("/tickets/{ticket_id}/subdivision", response_model=schemas.SubdivisionProposalOut | None)
def get_subdivision(ticket_id: int, db: Session = Depends(get_db)):
    _get_ticket(db, ticket_id)
    return db.scalars(
        select(SubdivisionProposal)
        .where(SubdivisionProposal.parent_ticket_id == ticket_id)
        .order_by(SubdivisionProposal.id.desc())
    ).first()


def _get_proposal(db: Session, proposal_id: int) -> SubdivisionProposal:
    prop = db.get(SubdivisionProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, f"Subdivision proposal {proposal_id} not found")
    return prop


@router.post("/subdivisions/{proposal_id}/approve", response_model=list[schemas.TicketOut])
def approve_subdivision(proposal_id: int, db: Session = Depends(get_db)):
    children = subdivision.approve(db, _get_proposal(db, proposal_id))
    db.commit()
    return children


@router.post("/subdivisions/{proposal_id}/reject", response_model=schemas.SubdivisionProposalOut)
def reject_subdivision(proposal_id: int, db: Session = Depends(get_db)):
    prop = subdivision.reject(db, _get_proposal(db, proposal_id))
    db.commit()
    db.refresh(prop)
    return prop


@router.post("/tickets/{ticket_id}/review", response_model=schemas.ReviewResult)
def review_ticket(ticket_id: int, body: schemas.ReviewRequest, db: Session = Depends(get_db)):
    ticket = _get_ticket(db, ticket_id)
    if ticket.status != "Reviewing":
        raise HTTPException(409, f"Ticket is '{ticket.status}', expected 'Reviewing' to review")
    ticket, rerun = review.review_ticket(db, ticket, body.satisfied, body.comment_md, body.actor)
    return schemas.ReviewResult(
        ticket=schemas.TicketOut.model_validate(ticket),
        rerun=schemas.AgentRunOut.model_validate(rerun) if rerun else None,
    )
