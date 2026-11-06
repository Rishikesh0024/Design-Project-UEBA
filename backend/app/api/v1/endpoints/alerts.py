"""Alerts CRUD, filtering, investigation, and review endpoints."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models_db.models import (
    Alert,
    AnalystReview,
    AppUser,
    AuditLog,
    ModelRun,
    UserProfile,
)
from app.schemas.schemas import AlertOut, AlertUpdate, ReviewOut

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _filtered_alerts(
    db: Session,
    dataset_id: Optional[int],
    severity: Optional[str],
    status: Optional[str],
    user_id: Optional[str],
    alert_id: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    min_risk: float,
):
    query = db.query(Alert)
    if dataset_id is not None:
        query = query.filter(Alert.dataset_id == dataset_id)
    if severity:
        query = query.filter(Alert.severity == severity.lower())
    if status:
        query = query.filter(Alert.status == status)
    if user_id:
        query = query.filter(Alert.user_id.ilike(f"%{user_id}%"))
    if alert_id:
        query = query.filter(Alert.alert_uid.ilike(f"%{alert_id}%"))
    if date_from:
        query = query.filter(Alert.created_at >= date_from)
    if date_to:
        query = query.filter(Alert.created_at <= date_to)
    return query.filter(Alert.risk_score >= min_risk)


@router.get("", response_model=list[AlertOut])
def list_alerts(
    dataset_id: Optional[int] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    alert_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    min_risk: float = Query(0.0),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    query = _filtered_alerts(
        db, dataset_id, severity, status, user_id, alert_id, date_from, date_to, min_risk
    )
    return query.order_by(Alert.risk_score.desc(), Alert.id.asc()).offset(offset).limit(limit).all()


@router.get("/paged")
def list_alerts_paged(
    dataset_id: int = Query(...),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    alert_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    query = _filtered_alerts(
        db, dataset_id, severity, status, user_id, alert_id, date_from, date_to, 0
    )
    total = query.count()
    items = (
        query.order_by(Alert.risk_score.desc(), Alert.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [AlertOut.model_validate(item) for item in items], "total": total}


@router.get("/summary")
def alert_summary(
    dataset_id: int = Query(...),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    query = _filtered_alerts(db, dataset_id, None, None, None, None, date_from, date_to, 0)
    total, average = query.with_entities(
        func.count(Alert.id), func.avg(Alert.risk_score)
    ).one()
    severity_rows = (
        query.with_entities(Alert.severity, func.count(Alert.id))
        .group_by(Alert.severity)
        .all()
    )
    score_bin = case(
        (Alert.risk_score < 25, "0–25"),
        (Alert.risk_score < 50, "25–50"),
        (Alert.risk_score < 75, "50–75"),
        else_="75–100",
    )
    score_rows = (
        query.with_entities(score_bin.label("score_range"), func.count(Alert.id))
        .group_by(score_bin)
        .all()
    )
    counts = {severity: count for severity, count in severity_rows}
    bins = {score_range: count for score_range, count in score_rows}
    return {
        "total_alerts": total,
        "average_risk_score": round(float(average), 2) if average is not None else 0,
        "severity_counts": {
            severity: counts.get(severity, 0)
            for severity in ("critical", "high", "medium", "low")
        },
        "score_distribution": [
            {"range": score_range, "count": bins.get(score_range, 0)}
            for score_range in ("0–25", "25–50", "50–75", "75–100")
        ],
    }


@router.get("/{alert_id}/investigation")
def get_investigation(
    alert_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    profile = (
        db.query(UserProfile)
        .filter(
            UserProfile.dataset_id == alert.dataset_id,
            UserProfile.user_id == alert.user_id,
        )
        .first()
    )
    model_run = db.get(ModelRun, alert.model_run_id)
    reviews = (
        db.query(AnalystReview)
        .filter(AnalystReview.alert_id == alert.id)
        .order_by(AnalystReview.reviewed_at.desc())
        .all()
    )
    return {
        "alert": AlertOut.model_validate(alert),
        "entity": {
            "user_id": alert.user_id,
            "role": profile.role if profile else None,
            "department": profile.department if profile else None,
            "total_events": profile.total_events if profile else None,
            "baseline": profile.baseline if profile else None,
        },
        "fusion_weights": (
            (model_run.train_config or {}).get("fusion_weights")
            if model_run is not None
            else None
        ),
        "reviews": [ReviewOut.model_validate(review) for review in reviews],
    }


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return alert


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(require_role("analyst", "admin")),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")

    if payload.status:
        alert.status = payload.status
    if payload.verdict:
        alert.verdict = payload.verdict

    if payload.note or payload.status or payload.verdict:
        review = AnalystReview(
            alert_id=alert.id,
            analyst_id=current_user.id if (current_user and current_user.id > 0) else None,
            status=payload.status or alert.status,
            verdict=payload.verdict,
            note=payload.note,
        )
        db.add(review)
        db.add(AuditLog(
            user_id=current_user.id if (current_user and current_user.id > 0) else None,
            action="update_alert",
            resource_type="alert",
            resource_id=str(alert_id),
            detail=payload.model_dump(exclude_none=True),
        ))

    db.commit()
    db.refresh(alert)
    return alert


@router.get("/{alert_id}/reviews", response_model=list[ReviewOut])
def get_reviews(
    alert_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    return (
        db.query(AnalystReview)
        .filter(AnalystReview.alert_id == alert_id)
        .order_by(AnalystReview.reviewed_at.desc())
        .all()
    )
