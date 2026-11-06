from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str
    role: Literal["analyst", "viewer"] = "analyst"

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DatasetOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    name: str
    version: str
    status: str
    total_rows: int
    valid_rows: int
    unique_users: int
    date_from: Optional[str]
    date_to: Optional[str]
    has_labels: bool
    is_demo: bool = False
    created_at: datetime


class DatasetDetail(DatasetOut):
    schema_info: Optional[dict] = None
    quality_report: Optional[dict] = None


class JobOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    dataset_id: int
    job_type: str
    status: str
    progress: int
    message: Optional[str] = None
    result: Optional[dict] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ModelRunOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    dataset_id: int
    branch: str
    status: str
    version: str
    train_config: Optional[dict] = None
    eval_metrics: Optional[dict] = None
    train_rows: int
    eval_rows: int
    created_at: datetime
    finished_at: Optional[datetime] = None


class AlertOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    alert_uid: str
    dataset_id: int
    user_id: str
    window_date: str
    primary_activity: str
    if_score: float
    stat_score: float
    rule_score: float
    risk_score: float
    temporal_score: float
    relational_score: float
    contextual_score: float
    severity: str
    threshold_value: float
    status: str
    verdict: Optional[str] = None
    rule_flags: Optional[list] = None
    explanation: Optional[str] = None
    label: int
    created_at: datetime
    evidence: list[AlertEvidenceOut] = Field(default_factory=list)


class AlertEvidenceOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    event_id: str
    activity: Optional[str] = None
    timestamp: Optional[datetime] = None
    resource: Optional[str] = None


class AlertUpdate(BaseModel):
    status: Optional[Literal["open", "investigating", "reviewed", "closed"]] = None
    verdict: Optional[Literal["confirmed_threat", "suspicious", "benign", "inconclusive"]] = None
    note: Optional[str] = Field(default=None, max_length=4000)


class ReviewOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    alert_id: int
    analyst_id: int
    status: str
    verdict: Optional[str] = None
    note: Optional[str] = None
    reviewed_at: datetime


class ThresholdOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    dataset_id: int
    role: Optional[str]
    quantile: float
    threshold_value: float
    sample_size: int
    is_active: bool
    created_at: datetime


class DriftEventOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    dataset_id: int
    branch: str
    detected_at: datetime
    window_start: Optional[str]
    window_end: Optional[str]
    score_before: Optional[float]
    score_after: Optional[float]
    notes: Optional[str]
    reviewed: bool


class UserProfileOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    dataset_id: int
    user_id: str
    role: Optional[str]
    department: Optional[str]
    total_events: int
    active_days: int
    baseline: Optional[dict]
    last_activity: Optional[datetime]


class ActivityEventOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    dataset_id: int
    event_id: str
    user_id: str
    activity: str
    timestamp: datetime
    pc: Optional[str] = None
    resource: Optional[str] = None
    label: int


class DetectionConfig(BaseModel):
    dataset_id: int
    train_fraction: float = Field(default=0.70, ge=0.5, le=0.9)
    contamination: float = Field(default=0.05, gt=0, le=0.2)
    min_risk_score: float = Field(default=25.0, ge=0, le=100)
    fusion_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "w_temporal": 0.40,
            "w_relational": 0.30,
            "w_contextual": 0.30,
        }
    )
    rule_thresholds: dict[str, float] = Field(default_factory=dict)


class EvalMetrics(BaseModel):
    precision: float
    recall: float
    f1_score: float
    false_positive_rate: float
    pr_auc: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


class DashboardStats(BaseModel):
    total_events: int
    unique_users: int
    total_alerts: int
    high_risk_alerts: int
    dataset_name: Optional[str]
    last_run: Optional[datetime]
