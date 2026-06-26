"""Board + status-block endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas, seed
from ..db import get_db
from ..models import Board, StatusBlock, Ticket

router = APIRouter(tags=["boards"])


def _get_board(db: Session, board_id: int) -> Board:
    board = db.get(Board, board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")
    return board


@router.get("/boards", response_model=list[schemas.BoardOut])
def list_boards(db: Session = Depends(get_db)):
    return db.scalars(select(Board).order_by(Board.id)).all()


@router.post("/boards", response_model=schemas.BoardOut, status_code=201)
def create_board(body: schemas.BoardCreate, db: Session = Depends(get_db)):
    board = Board(name=body.name, description=body.description)
    db.add(board)
    db.flush()
    if body.seed_default_statuses:
        seed.seed_statuses(db, board)
    db.commit()
    db.refresh(board)
    return board


@router.get("/boards/{board_id}", response_model=schemas.BoardOut)
def get_board(board_id: int, db: Session = Depends(get_db)):
    return _get_board(db, board_id)


@router.get("/boards/{board_id}/status-blocks", response_model=list[schemas.StatusBlockOut])
def list_status_blocks(board_id: int, db: Session = Depends(get_db)):
    _get_board(db, board_id)
    return db.scalars(
        select(StatusBlock).where(StatusBlock.board_id == board_id).order_by(StatusBlock.order_index)
    ).all()


@router.post("/boards/{board_id}/status-blocks", response_model=schemas.StatusBlockOut, status_code=201)
def add_status_block(board_id: int, body: schemas.StatusBlockCreate, db: Session = Depends(get_db)):
    _get_board(db, board_id)
    order_index = body.order_index
    if order_index is None:
        mx = db.scalar(select(func.max(StatusBlock.order_index)).where(StatusBlock.board_id == board_id))
        order_index = (mx + 1) if mx is not None else 0
    block = StatusBlock(
        board_id=board_id, name=body.name, color=body.color, order_index=order_index,
        is_agent_digestible=body.is_agent_digestible, is_terminal=body.is_terminal,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.patch("/status-blocks/{id}", response_model=schemas.StatusBlockOut)
def update_status_block(id: int, body: schemas.StatusBlockUpdate, db: Session = Depends(get_db)):
    block = db.get(StatusBlock, id)
    if block is None:
        raise HTTPException(404, f"Status block {id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(block, field, value)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/status-blocks/{id}", status_code=204)
def delete_status_block(id: int, db: Session = Depends(get_db)):
    block = db.get(StatusBlock, id)
    if block is None:
        raise HTTPException(404, f"Status block {id} not found")
    n = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.status_block_id == id)) or 0
    if n:
        raise HTTPException(409, f"Cannot delete: {n} ticket(s) are in '{block.name}'")
    db.delete(block)
    db.commit()
