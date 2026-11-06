"""
All SQLAlchemy ORM models for the UEBA platform.
Tables: app_users, datasets, processing_jobs, activity_events,
        user_profiles, model_runs, branch_scores, risk_scores,
        threshold_versions, drift_events, alerts, alert_evidence,
        analyst_reviews, audit_logs, baseline_updates
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import enum

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Index, Integer, JSON, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin    = "admin"
    analyst  = "analyst"
    viewer   = "viewer"


class DatasetStatus(str, enum.Enum):
    uploaded    = "uploaded"
    validating  = "validating"
    valid       = "valid"
    invalid     = "invalid"
    processing  = "processing"
    ready       = "ready"
    failed      = "failed"


class JobStatus(str, enum.Enum):
    pending   = "pending"
    running   = "running"
    completed = "completed"
    failed    = "failed"


class ModelStatus(str, enum.Enum):
    untrained = "untrained"
    training  = "training"
    ready     = "ready"
    failed    = "failed"


class AlertSeverity(str, enum.Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"


class AlertStatus(str, enum.Enum):
    open          = "open"
    investigating = "investigating"
    reviewed      = "reviewed"
    closed        = "closed"


class Verdict(str, enum.Enum):
    confirmed_threat = "confirmed_threat"
    suspicious       = "suspicious"
    benign           = "benign"
    inconclusive     = "inconclusive"


# ── Tables ────────────────────────────────────────────────────────────────────

class AppUser(Base):
    __tablename__ = "app_users"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    email:        Mapped[str]           = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name:    Mapped[str]           = mapped_column(String(255), nullable=False)
    hashed_pw:    Mapped[str]           = mapped_column(String(255), nullable=False)
    role:         Mapped[str]           = mapped_column(String(50), default=UserRole.analyst, nullable=False)
    is_active:    Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now)
    last_login:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    reviews:      Mapped[list[AnalystReview]] = relationship(back_populates="analyst")
    audit_logs:   Mapped[list[AuditLog]]      = relationship(back_populates="user")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        Index(
            "uq_demo_dataset_version",
            "version",
            unique=True,
            postgresql_where=text("is_demo IS TRUE"),
            sqlite_where=text("is_demo = 1"),
        ),
    )

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    name:         Mapped[str]      = mapped_column(String(255), nullable=False)
    version:      Mapped[str]      = mapped_column(String(50), default="r4.2")
    file_path:    Mapped[str]      = mapped_column(String(1024), nullable=False)
    status:       Mapped[str]      = mapped_column(String(50), default=DatasetStatus.uploaded)
    total_rows:   Mapped[int]      = mapped_column(Integer, default=0)
    valid_rows:   Mapped[int]      = mapped_column(Integer, default=0)
    unique_users: Mapped[int]      = mapped_column(Integer, default=0)
    date_from:    Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_to:      Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    has_labels:   Mapped[bool]     = mapped_column(Boolean, default=False)
    schema_info:  Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    quality_report: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_demo:      Mapped[bool]      = mapped_column(Boolean, default=False, nullable=False)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    uploaded_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("app_users.id"), nullable=True)

    jobs:         Mapped[list[ProcessingJob]] = relationship(back_populates="dataset")
    model_runs:   Mapped[list[ModelRun]]      = relationship(back_populates="dataset")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    job_type:     Mapped[str]      = mapped_column(String(100), nullable=False)
    status:       Mapped[str]      = mapped_column(String(50), default=JobStatus.pending)
    progress:     Mapped[int]      = mapped_column(Integer, default=0)
    message:      Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result:       Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    dataset:      Mapped[Dataset]  = relationship(back_populates="jobs")


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_ae_user_ts", "user_id", "timestamp"),
        Index("ix_ae_dataset", "dataset_id"),
    )

    id:           Mapped[int]      = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    event_id:     Mapped[str]      = mapped_column(String(100), nullable=False)
    user_id:      Mapped[str]      = mapped_column(String(100), nullable=False)
    activity:     Mapped[str]      = mapped_column(String(50), nullable=False)
    timestamp:    Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pc:           Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    resource:     Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    label:        Mapped[int]      = mapped_column(Integer, default=0)
    hour:         Mapped[int]      = mapped_column(Integer, default=0)
    day_of_week:  Mapped[int]      = mapped_column(Integer, default=0)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("dataset_id", "user_id"),)

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    user_id:      Mapped[str]      = mapped_column(String(100), nullable=False)
    role:         Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department:   Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_events: Mapped[int]      = mapped_column(Integer, default=0)
    active_days:  Mapped[int]      = mapped_column(Integer, default=0)
    baseline:     Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    branch:       Mapped[str]      = mapped_column(String(50), nullable=False)  # contextual|temporal|relational|fusion
    status:       Mapped[str]      = mapped_column(String(50), default=ModelStatus.untrained)
    version:      Mapped[str]      = mapped_column(String(50), nullable=False)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    train_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    eval_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    train_rows:   Mapped[int]      = mapped_column(Integer, default=0)
    eval_rows:    Mapped[int]      = mapped_column(Integer, default=0)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset:      Mapped[Dataset]  = relationship(back_populates="model_runs")
    branch_scores: Mapped[list[BranchScore]] = relationship(back_populates="model_run")


class BranchScore(Base):
    __tablename__ = "branch_scores"
    __table_args__ = (Index("ix_bs_user_date", "user_id", "window_date"),)

    id:           Mapped[int]      = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    model_run_id: Mapped[int]      = mapped_column(ForeignKey("model_runs.id"), nullable=False, index=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    user_id:      Mapped[str]      = mapped_column(String(100), nullable=False)
    window_date:  Mapped[str]      = mapped_column(String(20), nullable=False)
    branch:       Mapped[str]      = mapped_column(String(50), nullable=False)
    raw_score:    Mapped[float]    = mapped_column(Float, default=0.0)
    norm_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    in_train:     Mapped[bool]     = mapped_column(Boolean, default=False)
    label:        Mapped[int]      = mapped_column(Integer, default=0)

    model_run:    Mapped[ModelRun] = relationship(back_populates="branch_scores")


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (
        UniqueConstraint("model_run_id", "user_id", "window_date"),
        Index("ix_rs_user_date", "user_id", "window_date"),
    )

    id:           Mapped[int]      = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    model_run_id: Mapped[int]      = mapped_column(ForeignKey("model_runs.id"), nullable=False)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    user_id:      Mapped[str]      = mapped_column(String(100), nullable=False)
    window_date:  Mapped[str]      = mapped_column(String(20), nullable=False)
    if_score:     Mapped[float]    = mapped_column(Float, default=0.0)
    stat_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    rule_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    risk_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    temporal_score: Mapped[float]  = mapped_column(Float, default=0.0)
    relational_score: Mapped[float] = mapped_column(Float, default=0.0)
    contextual_score: Mapped[float] = mapped_column(Float, default=0.0)
    threshold_value: Mapped[float] = mapped_column(Float, default=25.0)
    severity:     Mapped[str]      = mapped_column(String(20), default="low")
    is_anomaly:   Mapped[bool]     = mapped_column(Boolean, default=False)
    in_train:     Mapped[bool]     = mapped_column(Boolean, default=False)
    label:        Mapped[int]      = mapped_column(Integer, default=0)
    fusion_weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class ThresholdVersion(Base):
    __tablename__ = "threshold_versions"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    role:         Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # None = global
    quantile:     Mapped[float]    = mapped_column(Float, default=0.95)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size:  Mapped[int]      = mapped_column(Integer, default=0)
    is_active:    Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by:   Mapped[Optional[int]] = mapped_column(ForeignKey("app_users.id"), nullable=True)


class DriftEvent(Base):
    __tablename__ = "drift_events"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    model_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_runs.id"), nullable=True)
    branch:       Mapped[str]      = mapped_column(String(50), nullable=False)
    detected_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    window_start: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    window_end:   Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    adwin_width:  Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_after:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes:        Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed:     Mapped[bool]     = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_user_date", "user_id", "window_date"),)

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    alert_uid:    Mapped[str]      = mapped_column(String(20), unique=True, nullable=False, index=True)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    model_run_id: Mapped[int]      = mapped_column(ForeignKey("model_runs.id"), nullable=False)
    user_id:      Mapped[str]      = mapped_column(String(100), nullable=False)
    window_date:  Mapped[str]      = mapped_column(String(20), nullable=False)
    primary_activity: Mapped[str]  = mapped_column(String(50), nullable=False)
    if_score:     Mapped[float]    = mapped_column(Float, default=0.0)
    stat_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    rule_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    risk_score:   Mapped[float]    = mapped_column(Float, default=0.0)
    temporal_score: Mapped[float]  = mapped_column(Float, default=0.0)
    relational_score: Mapped[float] = mapped_column(Float, default=0.0)
    contextual_score: Mapped[float] = mapped_column(Float, default=0.0)
    threshold_value: Mapped[float] = mapped_column(Float, default=25.0)
    severity:     Mapped[str]      = mapped_column(String(20), default=AlertSeverity.low)
    status:       Mapped[str]      = mapped_column(String(30), default=AlertStatus.open)
    verdict:      Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    rule_flags:   Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    explanation:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    label:        Mapped[int]      = mapped_column(Integer, default=0)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    evidence:     Mapped[list[AlertEvidence]]  = relationship(back_populates="alert", cascade="all, delete-orphan")
    reviews:      Mapped[list[AnalystReview]]  = relationship(back_populates="alert", cascade="all, delete-orphan")


class AlertEvidence(Base):
    __tablename__ = "alert_evidence"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    alert_id:     Mapped[int]      = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)
    event_id:     Mapped[str]      = mapped_column(String(100), nullable=False)
    activity:     Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timestamp:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resource:     Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    alert:        Mapped[Alert]    = relationship(back_populates="evidence")


class AnalystReview(Base):
    __tablename__ = "analyst_reviews"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    alert_id:     Mapped[int]      = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)
    analyst_id:   Mapped[int]      = mapped_column(ForeignKey("app_users.id"), nullable=False)
    status:       Mapped[str]      = mapped_column(String(30), nullable=False)
    verdict:      Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    note:         Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    alert:        Mapped[Alert]    = relationship(back_populates="reviews")
    analyst:      Mapped[AppUser]  = relationship(back_populates="reviews")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:           Mapped[int]      = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    user_id:      Mapped[Optional[int]] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    action:       Mapped[str]      = mapped_column(String(200), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id:  Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    detail:       Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address:   Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user:         Mapped[Optional[AppUser]] = relationship(back_populates="audit_logs")


class BaselineUpdate(Base):
    __tablename__ = "baseline_updates"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    user_id:      Mapped[str]      = mapped_column(String(100), nullable=False)
    dataset_id:   Mapped[int]      = mapped_column(ForeignKey("datasets.id"), nullable=False)
    approved_by:  Mapped[int]      = mapped_column(ForeignKey("app_users.id"), nullable=False)
    alert_id:     Mapped[Optional[int]] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    old_baseline: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_baseline: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reason:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
