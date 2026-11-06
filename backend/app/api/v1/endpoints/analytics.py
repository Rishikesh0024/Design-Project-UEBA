"""Analytics, dashboard stats, and evaluation metrics endpoints."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models_db.models import (
    AppUser, Alert, ActivityEvent, Dataset, ModelRun, RiskScore, DriftEvent
)
from app.schemas.schemas import DashboardStats

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats(
    dataset_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    q_events = db.query(func.count(ActivityEvent.id))
    q_users  = db.query(func.count(func.distinct(ActivityEvent.user_id)))
    q_alerts = db.query(func.count(Alert.id))
    q_high   = db.query(func.count(Alert.id)).filter(Alert.severity.in_(["critical", "high"]))

    if dataset_id:
        q_events = q_events.filter(ActivityEvent.dataset_id == dataset_id)
        q_users  = q_users.filter(ActivityEvent.dataset_id == dataset_id)
        q_alerts = q_alerts.filter(Alert.dataset_id == dataset_id)
        q_high   = q_high.filter(Alert.dataset_id == dataset_id)

    ds = db.get(Dataset, dataset_id) if dataset_id else None
    last_run = (
        db.query(ModelRun.finished_at)
        .filter(ModelRun.dataset_id == dataset_id)
        .order_by(ModelRun.finished_at.desc())
        .scalar()
        if dataset_id else None
    )

    return DashboardStats(
        total_events=q_events.scalar() or 0,
        unique_users=q_users.scalar() or 0,
        total_alerts=q_alerts.scalar() or 0,
        high_risk_alerts=q_high.scalar() or 0,
        dataset_name=ds.name if ds else None,
        last_run=last_run,
    )


@router.get("/activity-over-time")
def activity_over_time(
    dataset_id: int = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    rows = (
        db.query(
            func.date(ActivityEvent.timestamp).label("date"),
            ActivityEvent.activity,
            func.count(ActivityEvent.id).label("count"),
        )
        .filter(ActivityEvent.dataset_id == dataset_id)
        .group_by(func.date(ActivityEvent.timestamp), ActivityEvent.activity)
        .order_by(func.date(ActivityEvent.timestamp))
        .all()
    )
    return [{"date": str(r.date), "activity": r.activity, "count": r.count} for r in rows]


@router.get("/risk-distribution")
def risk_distribution(
    dataset_id: int = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    rows = (
        db.query(RiskScore.risk_score, RiskScore.is_anomaly)
        .join(ModelRun, RiskScore.model_run_id == ModelRun.id)
        .filter(RiskScore.dataset_id == dataset_id, RiskScore.in_train == False)
        .all()
    )
    return [{"risk_score": r.risk_score, "is_anomaly": r.is_anomaly} for r in rows]


@router.get("/alerts-over-time")
def alerts_over_time(
    dataset_id: int = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    rows = (
        db.query(Alert.window_date, Alert.severity, func.count(Alert.id).label("count"))
        .filter(Alert.dataset_id == dataset_id)
        .group_by(Alert.window_date, Alert.severity)
        .order_by(Alert.window_date)
        .all()
    )
    return [{"date": r.window_date, "severity": r.severity, "count": r.count} for r in rows]


@router.get("/drift-history")
def drift_history(
    dataset_id: int = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    rows = (
        db.query(DriftEvent)
        .filter(DriftEvent.dataset_id == dataset_id)
        .order_by(DriftEvent.detected_at.desc())
        .limit(100)
        .all()
    )
    return rows
