from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import Strategy
from .orm import SavedStrategy, User

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    definition: Strategy


class StrategyOut(BaseModel):
    id: int
    name: str
    description: str | None
    definition: Strategy
    createdAt: datetime
    updatedAt: datetime


def _out(s: SavedStrategy) -> StrategyOut:
    return StrategyOut(id=s.id, name=s.name, description=s.description,
                       definition=Strategy.model_validate(s.definition),
                       createdAt=s.created_at, updatedAt=s.updated_at)


def _get(db: Session, user: User, strategy_id: int) -> SavedStrategy:
    s = db.scalar(select(SavedStrategy).where(SavedStrategy.id == strategy_id, SavedStrategy.user_id == user.id))
    if s is None:
        raise HTTPException(404, detail={"error": "not_found", "message": "Strategy not found."})
    return s


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail={"error": "name_taken", "message": "You already have a strategy with this name."})


@router.get("", response_model=list[StrategyOut])
def list_strategies(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(SavedStrategy).where(SavedStrategy.user_id == user.id).order_by(SavedStrategy.updated_at.desc()))
    return [_out(r) for r in rows]


@router.post("", response_model=StrategyOut, status_code=201)
def create_strategy(body: StrategyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = SavedStrategy(user_id=user.id, name=body.name.strip(), description=body.description,
                      definition=body.definition.model_dump(mode="json"))
    db.add(s)
    _commit(db)
    return _out(s)


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _out(_get(db, user, strategy_id))


@router.put("/{strategy_id}", response_model=StrategyOut)
def update_strategy(strategy_id: int, body: StrategyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _get(db, user, strategy_id)
    s.name, s.description = body.name.strip(), body.description
    s.definition = body.definition.model_dump(mode="json")
    _commit(db)
    db.refresh(s)
    return _out(s)


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_get(db, user, strategy_id))
    db.commit()
    return Response(status_code=204)
