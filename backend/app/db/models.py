"""
SQLAlchemy ORM models for UEBA.
All timestamps are stored as UTC ISO-8601 strings for SQLite compatibility.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.db.session import Base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Dataset & Processing
# ---------------------------------------------------------------------------

class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    filename = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    uploaded_at = Column(String(50), default=_now)
    status = Column(String(50), default="uploaded")   # uploaded|processing|ready|error
    total_rows = Column(Integer, default=0)
    valid_rows = Column(Integer, default=0)
    skipped_rows = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    column_mapping = Column(Text, nullable=True)       # JSON string
    is_demo = Column(Boolean, default=False)

    events = relationship("ActivityEvent", back_populates="dataset", cascade="all, delete-orphan")
    detection_runs = relationship("DetectionRun", back_populates="dataset", cascade="all, delete-orphan")


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    started_at = Column(String(50), default=_now)
    finished_at = Column(String(50), nullable=True)
    status = Column(String(50), default="running")    # running|completed|failed
    events_processed = Column(Integer, default=0)
    users_profiled = Column(Integer, default=0)
    log = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Activity Events
# ---------------------------------------------------------------------------

class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    original_id = Column(String(128), nullable=True)   # source event id
    user_id = Column(String(128), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)  # logon|logoff|file|email|web|device
    timestamp = Column(String(50), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=True)       # 0=Mon … 6=Sun
    hour_of_day = Column(Integer, nullable=True)
    pc = Column(String(128), nullable=True)
    resource = Column(String(512), nullable=True)
    activity = Column(String(256), nullable=True)
    raw_json = Column(Text, nullable=True)             # original row as JSON

    dataset = relationship("Dataset", back_populates="events")
    __table_args__ = (
        Index("ix_ae_user_ts", "user_id", "timestamp"),
    )


# ---------------------------------------------------------------------------
# User & Role Metadata
# ---------------------------------------------------------------------------

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(128), unique=True, nullable=False, index=True)
    role = Column(String(128), nullable=True)
    department = Column(String(128), nullable=True)
    team = Column(String(128), nullable=True)
    first_seen = Column(String(50), nullable=True)
    last_seen = Column(String(50), nullable=True)
    total_events = Column(Integer, default=0)
    # Baseline features stored as JSON
    baseline_json = Column(Text, nullable=True)
    baseline_computed_at = Column(String(50), nullable=True)
    baseline_window_days = Column(Integer, default=30)


class RoleBaseline(Base):
    __tablename__ = "role_baselines"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(128), unique=True, nullable=False, index=True)
    baseline_json = Column(Text, nullable=True)
    computed_at = Column(String(50), nullable=True)
    user_count = Column(Integer, default=0)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class DetectionRun(Base):
    __tablename__ = "detection_runs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    started_at = Column(String(50), default=_now)
    finished_at = Column(String(50), nullable=True)
    status = Column(String(50), default="running")
    model_version = Column(String(64), nullable=True)
    config_json = Column(Text, nullable=True)          # scoring weights etc.
    total_windows = Column(Integer, default=0)
    anomalies_found = Column(Integer, default=0)
    log = Column(Text, nullable=True)

    dataset = relationship("Dataset", back_populates="detection_runs")
    alerts = relationship("Alert", back_populates="detection_run", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    detection_run_id = Column(Integer, ForeignKey("detection_runs.id"), nullable=False)
    user_id = Column(String(128), nullable=False, index=True)
    event_date = Column(String(20), nullable=False, index=True)   # YYYY-MM-DD
    event_type = Column(String(64), nullable=True)
    risk_score = Column(Float, nullable=False)
    severity = Column(String(20), nullable=False, index=True)     # critical|high|medium|low
    explanation = Column(Text, nullable=False)
    feature_deviations_json = Column(Text, nullable=True)         # JSON
    event_ids_json = Column(Text, nullable=True)                  # JSON list of ActivityEvent ids
    model_signal = Column(String(128), nullable=True)
    if_score = Column(Float, nullable=True)                       # raw Isolation Forest score
    stat_score = Column(Float, nullable=True)                     # statistical deviation score
    rule_flags_json = Column(Text, nullable=True)                 # JSON list of triggered rules
    created_at = Column(String(50), default=_now)

    # Investigation
    status = Column(String(30), default="open")   # open|investigating|reviewed
    verdict = Column(String(20), nullable=True)   # benign|suspicious|None
    reviewed_at = Column(String(50), nullable=True)
    reviewed_by = Column(String(128), nullable=True)

    detection_run = relationship("DetectionRun", back_populates="alerts")
    notes = relationship("AlertNote", back_populates="alert", cascade="all, delete-orphan")
    evidence = relationship("AlertEvidence", back_populates="alert", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("detection_run_id", "user_id", "event_date", "event_type",
                         name="uq_alert_window"),
    )


class AlertNote(Base):
    __tablename__ = "alert_notes"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    author = Column(String(128), default="analyst")
    note = Column(Text, nullable=False)
    created_at = Column(String(50), default=_now)

    alert = relationship("Alert", back_populates="notes")


class AlertEvidence(Base):
    __tablename__ = "alert_evidence"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("activity_events.id"), nullable=True)
    description = Column(Text, nullable=True)

    alert = relationship("Alert", back_populates="evidence")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id = Column(Integer, primary_key=True, index=True)
    detection_run_id = Column(Integer, ForeignKey("detection_runs.id"), nullable=False)
    computed_at = Column(String(50), default=_now)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    false_positive_rate = Column(Float, nullable=True)
    true_positives = Column(Integer, nullable=True)
    false_positives = Column(Integer, nullable=True)
    true_negatives = Column(Integer, nullable=True)
    false_negatives = Column(Integer, nullable=True)
    pr_auc = Column(Float, nullable=True)
    confusion_matrix_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(String(50), default=_now)
