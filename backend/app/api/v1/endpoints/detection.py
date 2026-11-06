"""Detection pipeline execution endpoint."""
from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models_db.models import AppUser, Dataset, ModelRun, ProcessingJob
from app.schemas.schemas import DetectionConfig, JobOut, ModelRunOut
from app.services.detection_service import run_detection_pipeline
from app.models_db.models import RiskScore

router = APIRouter(prefix="/detection", tags=["detection"])


@router.post("/run", response_model=JobOut, status_code=202)
def run_detection(
    config: DetectionConfig,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ds = db.get(Dataset, config.dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    if ds.status != "ready":
        raise HTTPException(400, f"Dataset not ready (status={ds.status})")

    job = ProcessingJob(
        dataset_id=config.dataset_id,
        job_type="detection",
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_detection_pipeline, job.id, config.model_dump())
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/runs/{dataset_id}", response_model=list[ModelRunOut])
def list_runs(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    return (
        db.query(ModelRun)
        .filter(ModelRun.dataset_id == dataset_id)
        .order_by(ModelRun.created_at.desc())
        .all()
    )


@router.get("/scores/{dataset_id}")
def list_risk_scores(
    dataset_id: int,
    model_run_id: int | None = None,
    user_id: str | None = None,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    query = db.query(RiskScore).filter(
        RiskScore.dataset_id == dataset_id,
        RiskScore.in_train.is_(False),
    )
    if model_run_id is not None:
        query = query.filter(RiskScore.model_run_id == model_run_id)
    if user_id:
        query = query.filter(RiskScore.user_id == user_id)
    total = query.count()
    rows = (
        query.order_by(RiskScore.risk_score.desc())
        .offset(offset)
        .limit(min(max(limit, 1), 1000))
        .all()
    )
    return {
        "items": [
            {
                "user_id": row.user_id,
                "window_date": row.window_date,
                "temporal_score": row.temporal_score,
                "relational_score": row.relational_score,
                "contextual_score": row.contextual_score,
                "risk_score": row.risk_score,
                "threshold_value": row.threshold_value,
                "severity": row.severity,
                "is_anomaly": row.is_anomaly,
                "label": row.label,
            }
            for row in rows
        ],
        "total": total,
    }


@router.get("/summary/{dataset_id}")
def detection_summary(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    latest_run_id = db.query(func.max(ModelRun.id)).filter(
        ModelRun.dataset_id == dataset_id,
        ModelRun.status == "ready",
    ).scalar()
    if latest_run_id is None:
        return {"scored_windows": 0, "normal_windows": 0, "anomalous_windows": 0}
    query = db.query(RiskScore).filter(
        RiskScore.dataset_id == dataset_id,
        RiskScore.model_run_id == latest_run_id,
        RiskScore.in_train.is_(False),
    )
    return {
        "scored_windows": query.count(),
        "normal_windows": query.filter(RiskScore.is_anomaly.is_(False)).count(),
        "anomalous_windows": query.filter(RiskScore.is_anomaly.is_(True)).count(),
    }
