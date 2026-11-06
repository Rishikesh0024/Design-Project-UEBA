"""User profiles and behaviour baseline endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models_db.models import AppUser, UserProfile, ActivityEvent, Alert
from app.schemas.schemas import AlertOut, UserProfileOut

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[UserProfileOut])
def list_profiles(
    dataset_id: int = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    return (
        db.query(UserProfile)
        .filter(UserProfile.dataset_id == dataset_id)
        .order_by(UserProfile.total_events.desc())
        .all()
    )


@router.get("/user/detail", response_model=UserProfileOut)
def get_profile_by_query(
    dataset_id: int = Query(...),
    user_id: str = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    p = (
        db.query(UserProfile)
        .filter(UserProfile.dataset_id == dataset_id, UserProfile.user_id == user_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Profile not found")
    return p


@router.get("/user/events")
def get_user_events_by_query(
    dataset_id: int = Query(...),
    user_id: str = Query(...),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    rows = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.dataset_id == dataset_id, ActivityEvent.user_id == user_id)
        .order_by(ActivityEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "event_id": r.event_id, "activity": r.activity,
            "timestamp": r.timestamp.isoformat(), "pc": r.pc,
            "resource": r.resource, "label": r.label,
        }
        for r in rows
    ]


@router.get("/user/alerts", response_model=list[AlertOut])
def get_user_alerts_by_query(
    dataset_id: int = Query(...),
    user_id: str = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    return (
        db.query(Alert)
        .filter(Alert.dataset_id == dataset_id, Alert.user_id == user_id)
        .order_by(Alert.risk_score.desc())
        .all()
    )


@router.get("/{dataset_id}/{user_id:path}/events")
def get_user_events(
    dataset_id: int,
    user_id: str,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    rows = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.dataset_id == dataset_id, ActivityEvent.user_id == user_id)
        .order_by(ActivityEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "event_id": r.event_id, "activity": r.activity,
            "timestamp": r.timestamp.isoformat(), "pc": r.pc,
            "resource": r.resource, "label": r.label,
        }
        for r in rows
    ]


@router.get("/{dataset_id}/{user_id:path}/alerts")
def get_user_alerts(
    dataset_id: int,
    user_id: str,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
) -> list[AlertOut]:
    return (
        db.query(Alert)
        .filter(Alert.dataset_id == dataset_id, Alert.user_id == user_id)
        .order_by(Alert.risk_score.desc())
        .all()
    )


@router.get("/{dataset_id}/{user_id:path}", response_model=UserProfileOut)
def get_profile(
    dataset_id: int,
    user_id: str,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    p = (
        db.query(UserProfile)
        .filter(UserProfile.dataset_id == dataset_id, UserProfile.user_id == user_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Profile not found")
    return p
