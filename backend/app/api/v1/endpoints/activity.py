from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models_db.models import ActivityEvent, AppUser, Dataset
from app.schemas.schemas import ActivityEventOut

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/events")
def list_events(
    dataset_id: int = Query(...),
    user_id: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None),
    activity: Optional[list[str]] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    query = db.query(ActivityEvent).filter(ActivityEvent.dataset_id == dataset_id)
    if user_id:
        query = query.filter(ActivityEvent.user_id.ilike(f"%{user_id}%"))
    if event_id:
        query = query.filter(ActivityEvent.event_id.ilike(f"%{event_id}%"))
    if activity:
        query = query.filter(ActivityEvent.activity.in_(activity))
    if date_from:
        query = query.filter(ActivityEvent.timestamp >= date_from)
    if date_to:
        query = query.filter(ActivityEvent.timestamp <= date_to)
    total = query.with_entities(func.count(ActivityEvent.id)).scalar() or 0
    rows = (
        query.order_by(ActivityEvent.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [ActivityEventOut.model_validate(row) for row in rows], "total": total}


@router.get("/events/{dataset_id}/{event_id}", response_model=ActivityEventOut)
def get_event(
    dataset_id: int,
    event_id: str,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    event = (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.dataset_id == dataset_id,
            ActivityEvent.event_id == event_id,
        )
        .first()
    )
    if event is None:
        raise HTTPException(404, "Event not found")
    return event
