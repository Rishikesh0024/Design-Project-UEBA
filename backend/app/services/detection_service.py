from __future__ import annotations

import logging
import resource
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models_db.models import (
    ActivityEvent,
    Alert,
    AlertEvidence,
    Dataset,
    ModelRun,
    ProcessingJob,
    RiskScore,
    ThresholdVersion,
    UserProfile,
)

logger = logging.getLogger(__name__)
DEFAULT_WEIGHTS = {"w_temporal": 0.4, "w_relational": 0.3, "w_contextual": 0.3}
FEATURES = (
    "total_events", "logon_count", "file_count", "email_count",
    "web_count", "device_count", "after_hours_ratio", "distinct_resources",
)
MIN_PERSONAL_HISTORY = 7


def _branch_scores(events: pd.DataFrame, train_fraction: float) -> tuple[pd.DataFrame, dict]:
    dates = sorted(events["date"].unique())
    if len(dates) < 2:
        raise ValueError("Detection requires events across at least two calendar days.")
    split = min(max(int(len(dates) * train_fraction), 1), len(dates) - 1)
    train_end = dates[split - 1]
    events = events.sort_values(["user", "timestamp"]).copy()
    events["in_train"] = events["date"] <= train_end
    train_events = events[events["in_train"]]
    events["previous_activity"] = events.groupby("user")["activity"].shift()

    transition_counts = Counter(
        (str(previous), str(current))
        for previous, current in zip(
            train_events.groupby("user")["activity"].shift(),
            train_events["activity"],
        )
        if pd.notna(previous)
    )
    previous_counts = Counter()
    for (previous, _current), count in transition_counts.items():
        previous_counts[previous] += count
    activity_count = max(int(train_events["activity"].nunique()), 1)
    events["temporal_score"] = events.apply(
        lambda row: 1.0 - (
            transition_counts.get((row["previous_activity"], row["activity"]), 0) + 1
        ) / (
            previous_counts.get(row["previous_activity"], 0) + activity_count
        ) if pd.notna(row["previous_activity"]) else 0.5,
        axis=1,
    ).clip(0, 1)

    events["resource_key"] = events["resource"].where(
        events["resource"].astype(str).str.strip().ne(""),
        events["pc"].fillna(""),
    )
    train_edges = Counter(zip(
        events.loc[events["in_train"], "user"].astype(str),
        events.loc[events["in_train"], "resource_key"].astype(str),
    ))
    events["relational_score"] = events.apply(
        lambda row: 1.0 / (1.0 + train_edges.get(
            (str(row["user"]), str(row["resource_key"])), 0
        )),
        axis=1,
    )

    events["is_after_hours"] = (
        (events["timestamp"].dt.hour >= 18) | (events["timestamp"].dt.hour < 8)
    ).astype(int)
    events["is_logon"] = events["activity"].isin(["logon", "logoff"]).astype(int)
    events["is_file"] = events["activity"].eq("file").astype(int)
    events["is_email"] = events["activity"].eq("email").astype(int)
    events["is_web"] = events["activity"].eq("web").astype(int)
    events["is_device"] = events["activity"].eq("device").astype(int)
    grouped = events.groupby(["user", "date"], sort=False)
    daily = grouped.agg(
        total_events=("event_id", "size"),
        logon_count=("is_logon", "sum"),
        file_count=("is_file", "sum"),
        email_count=("is_email", "sum"),
        web_count=("is_web", "sum"),
        device_count=("is_device", "sum"),
        after_hours_count=("is_after_hours", "sum"),
        distinct_resources=("resource_key", "nunique"),
        label=("label", "max"),
        in_train=("in_train", "max"),
        temporal_score=("temporal_score", "mean"),
        relational_score=("relational_score", "mean"),
    ).reset_index()
    daily["after_hours_ratio"] = daily["after_hours_count"] / daily["total_events"].clip(lower=1)

    training = daily[daily["in_train"]]
    user_baselines: dict[str, dict[str, tuple[float, float]]] = {}
    user_history_counts: dict[str, int] = {}
    for user, group in training.groupby("user"):
        user_history_counts[str(user)] = len(group)
        user_baselines[str(user)] = {
            feature: (
                float(group[feature].median()),
                float((group[feature] - group[feature].median()).abs().median()),
            )
            for feature in FEATURES
        }
    role_lookup = (
        events[["user", "role"]].drop_duplicates("user").set_index("user")["role"].to_dict()
    )
    role_baselines: dict[str, dict[str, tuple[float, float]]] = {}
    training_with_role = training.copy()
    training_with_role["role"] = training_with_role["user"].map(role_lookup)
    for role, group in training_with_role.dropna(subset=["role"]).groupby("role"):
        role_baselines[str(role)] = {
            feature: (
                float(group[feature].median()),
                float((group[feature] - group[feature].median()).abs().median()),
            )
            for feature in FEATURES
        }
    global_baseline = {
        feature: (
            float(training[feature].median()),
            float((training[feature] - training[feature].median()).abs().median()),
        )
        for feature in FEATURES
    }

    def contextual_score(row: pd.Series) -> float:
        role = role_lookup.get(row["user"])
        user_key = str(row["user"])
        if user_history_counts.get(user_key, 0) >= MIN_PERSONAL_HISTORY:
            baseline = user_baselines[user_key]
        else:
            baseline = role_baselines.get(str(role), global_baseline)
        deviations = []
        for feature in FEATURES:
            median, mad = baseline[feature]
            deviations.append(max(0.0, (float(row[feature]) - median) / max(mad, 1.0)))
        return float(np.clip(np.mean(deviations) / 5.0, 0, 1))

    daily["contextual_score"] = daily.apply(contextual_score, axis=1)
    return daily, {
        "train_end": str(train_end),
        "roles": role_lookup,
        "user_baselines": user_baselines,
        "user_history_counts": user_history_counts,
        "role_baselines": role_baselines,
        "global_baseline": global_baseline,
        "training_rows": len(training),
    }


def _evaluate(scored: pd.DataFrame) -> dict | None:
    evaluation = scored[~scored["in_train"]].copy()
    if evaluation.empty or not evaluation["label"].astype(int).any():
        return None
    truth = evaluation["label"].astype(int).to_numpy()
    predicted = evaluation["is_anomaly"].astype(int).to_numpy()
    score = evaluation["risk_score"].to_numpy()
    tn, fp, fn, tp = confusion_matrix(truth, predicted, labels=[0, 1]).ravel()
    k = min(max(int(np.ceil(len(evaluation) * 0.05)), 1), len(evaluation))
    top_k = evaluation.nlargest(k, "risk_score")
    delays = []
    for _, user_rows in evaluation.groupby("user"):
        positive_days = user_rows.loc[user_rows["label"].eq(1), "date"]
        detected_days = user_rows.loc[
            user_rows["label"].eq(1) & user_rows["is_anomaly"], "date"
        ]
        if not positive_days.empty and not detected_days.empty:
            delays.append(max(
                (pd.Timestamp(detected_days.min()) - pd.Timestamp(positive_days.min())).days,
                0,
            ))
    delay = float(np.mean(delays)) if delays else None
    metrics = {
        "precision": float(precision_score(truth, predicted, zero_division=0)),
        "recall": float(recall_score(truth, predicted, zero_division=0)),
        "f1_score": float(f1_score(truth, predicted, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
        "pr_auc": float(average_precision_score(truth, score)),
        "top_k_precision": float(top_k["label"].mean()),
        "top_k": k,
        "detection_delay_days": delay,
        "alert_volume": int(predicted.sum()),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "support_positive": int(truth.sum()),
        "support_negative": int((truth == 0).sum()),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }
    if np.unique(truth).size == 2:
        false_positive_rates, true_positive_rates, _ = roc_curve(truth, score)
        precisions, recalls, _ = precision_recall_curve(truth, score)
        metrics["roc_auc"] = float(roc_auc_score(truth, score))
        metrics["roc_curve"] = [
            _sample_curve(false_positive_rates),
            _sample_curve(true_positive_rates),
        ]
        metrics["precision_recall_curve"] = [
            _sample_curve(recalls),
            _sample_curve(precisions),
        ]
    return metrics


def _sample_curve(values: np.ndarray, max_points: int = 201) -> list[float]:
    if len(values) <= max_points:
        return [float(value) for value in values]
    indices = np.linspace(0, len(values) - 1, max_points, dtype=int)
    return [float(values[index]) for index in indices]


def run_detection_pipeline(job_id: int, config: dict) -> None:
    started = time.perf_counter()
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            logger.error("Detection requested for missing job %s", job_id)
            return
        try:
            job.status = "running"
            job.progress = 5
            job.message = "Loading dataset events"
            db.commit()
            dataset = db.get(Dataset, job.dataset_id)
            rows = db.scalars(
                select(ActivityEvent)
                .where(ActivityEvent.dataset_id == job.dataset_id)
                .order_by(ActivityEvent.timestamp)
            ).all()
            if dataset is None or not rows:
                raise ValueError("The selected dataset has no ingested activity events.")

            profiles = db.scalars(
                select(UserProfile).where(UserProfile.dataset_id == job.dataset_id)
            ).all()
            roles = {profile.user_id: profile.role for profile in profiles if profile.role}
            events = pd.DataFrame([{
                "event_id": row.event_id,
                "timestamp": row.timestamp,
                "user": row.user_id,
                "activity": row.activity,
                "pc": row.pc,
                "resource": row.resource,
                "label": row.label,
                "role": roles.get(row.user_id),
            } for row in rows])
            events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True)
            events["date"] = events["timestamp"].dt.date

            job.progress = 20
            job.message = "Building temporal, relational, and robust context scores"
            db.commit()
            scored, baseline_info = _branch_scores(
                events, float(config.get("train_fraction", 0.7))
            )
            for profile in profiles:
                role = baseline_info["roles"].get(profile.user_id)
                if baseline_info["user_history_counts"].get(profile.user_id, 0) >= MIN_PERSONAL_HISTORY:
                    stats = baseline_info["user_baselines"][profile.user_id]
                    source = "user"
                elif role in baseline_info["role_baselines"]:
                    stats = baseline_info["role_baselines"][role]
                    source = f"role:{role}"
                else:
                    stats = baseline_info["global_baseline"]
                    source = "global"
                profile.baseline = {
                    feature: {"median": values[0], "mad": values[1], "source": source}
                    for feature, values in stats.items()
                }
                profile.baseline["baseline_source"] = source
            weights = {
                **DEFAULT_WEIGHTS,
                **{
                    key: float(value)
                    for key, value in config.get("fusion_weights", {}).items()
                    if key in DEFAULT_WEIGHTS
                },
            }
            weight_total = sum(weights.values())
            if weight_total <= 0:
                raise ValueError("At least one fusion weight must be greater than zero.")
            weights = {key: value / weight_total for key, value in weights.items()}
            scored["risk_score"] = 100 * sum(
                scored[score_key] * weight
                for score_key, weight in zip(
                    ("temporal_score", "relational_score", "contextual_score"),
                    weights.values(),
                )
            )

            train_scores = scored.loc[scored["in_train"], "risk_score"]
            if train_scores.empty:
                raise ValueError("No training windows are available for threshold calibration.")
            threshold_global = max(
                float(config.get("min_risk_score", 25)),
                float(train_scores.quantile(0.95)),
            )
            user_roles = baseline_info["roles"]
            thresholds: dict[str, float] = {}
            for role in set(user_roles.values()):
                if role is None:
                    continue
                role_users = [user for user, value in user_roles.items() if value == role]
                role_train = scored[
                    scored["in_train"] & scored["user"].isin(role_users)
                ]["risk_score"]
                if len(role_train) >= 10:
                    thresholds[str(role)] = max(
                        float(config.get("min_risk_score", 25)),
                        float(role_train.quantile(0.95)),
                    )
            scored["threshold"] = scored["user"].map(
                lambda user: thresholds.get(str(user_roles.get(user)), threshold_global)
            )
            scored["is_anomaly"] = (
                ~scored["in_train"] & (scored["risk_score"] >= scored["threshold"])
            )
            scored["severity"] = pd.cut(
                scored["risk_score"],
                bins=[-1, 25, 50, 75, 100.01],
                labels=["low", "medium", "high", "critical"],
            ).astype(str)

            model_run = ModelRun(
                dataset_id=job.dataset_id,
                branch="fusion",
                status="training",
                version="three-branch-empirical-v1",
                train_config={
                    **config,
                    "fusion_weights": weights,
                    "threshold_global": threshold_global,
                    "role_thresholds": thresholds,
                    "branch_implementations": {
                        "temporal": "empirical next-event transition surprise",
                        "relational": "historical user-resource edge novelty",
                        "contextual": "user/role median and MAD deviations",
                        "limitations": (
                            "Causal Transformer, HGT relation decoder, and ADWIN "
                            "are not implemented in this release."
                        ),
                    },
                },
                train_rows=int(scored["in_train"].sum()),
                eval_rows=int((~scored["in_train"]).sum()),
            )
            db.add(model_run)
            db.flush()
            job.progress = 45
            job.message = "Persisting branch scores and fused risk windows"
            db.commit()

            threshold_rows = [ThresholdVersion(
                dataset_id=job.dataset_id,
                role=None,
                quantile=0.95,
                threshold_value=threshold_global,
                sample_size=int(scored["in_train"].sum()),
                is_active=True,
            )]
            threshold_rows.extend(
                ThresholdVersion(
                    dataset_id=job.dataset_id,
                    role=role,
                    quantile=0.95,
                    threshold_value=value,
                    sample_size=int(
                        ((scored["user"].map(user_roles) == role) & scored["in_train"]).sum()
                    ),
                    is_active=True,
                )
                for role, value in thresholds.items()
            )
            db.add_all(threshold_rows)

            risk_rows = []
            alerts = []
            minimum = float(config.get("min_risk_score", 25))
            for row in scored.to_dict(orient="records"):
                risk = float(row["risk_score"])
                score = RiskScore(
                    model_run_id=model_run.id,
                    dataset_id=job.dataset_id,
                    user_id=str(row["user"]),
                    window_date=str(row["date"]),
                    temporal_score=float(row["temporal_score"]),
                    relational_score=float(row["relational_score"]),
                    contextual_score=float(row["contextual_score"]),
                    threshold_value=float(row["threshold"]),
                    risk_score=risk,
                    severity=row["severity"],
                    is_anomaly=bool(row["is_anomaly"]),
                    in_train=bool(row["in_train"]),
                    label=int(row["label"]),
                    fusion_weights=weights,
                )
                risk_rows.append(score)
                if not row["is_anomaly"] or risk < minimum:
                    continue
                user_events = events[
                    (events["user"] == row["user"])
                    & (events["date"] == row["date"])
                ]
                primary_activity = (
                    str(user_events["activity"].mode().iloc[0])
                    if not user_events.empty else "unknown"
                )
                alert = Alert(
                    alert_uid=uuid4().hex[:16],
                    dataset_id=job.dataset_id,
                    model_run_id=model_run.id,
                    user_id=str(row["user"]),
                    window_date=str(row["date"]),
                    primary_activity=primary_activity,
                    temporal_score=float(row["temporal_score"]),
                    relational_score=float(row["relational_score"]),
                    contextual_score=float(row["contextual_score"]),
                    threshold_value=float(row["threshold"]),
                    risk_score=risk,
                    severity=row["severity"],
                    status="open",
                    rule_flags=[],
                    explanation=(
                        f"Fused score {risk:.1f} exceeded the "
                        f"{row['threshold']:.1f} threshold. "
                        f"Temporal {row['temporal_score']:.2f}, relational "
                        f"{row['relational_score']:.2f}, contextual "
                        f"{row['contextual_score']:.2f}."
                    ),
                    label=int(row["label"]),
                )
                alert.evidence = [
                    AlertEvidence(
                        event_id=str(event["event_id"]),
                        activity=str(event["activity"]),
                        timestamp=event["timestamp"].to_pydatetime(),
                        resource=str(event["resource"]) if event["resource"] else None,
                    )
                    for event in user_events.head(100).to_dict(orient="records")
                ]
                alerts.append(alert)

            db.add_all(risk_rows)
            db.add_all(alerts)
            db.flush()
            job.progress = 80
            job.message = "Computing evaluation metrics when held-out labels exist"
            db.commit()

            metrics = _evaluate(scored)
            memory_divisor = 1024 ** 2 if sys.platform == "darwin" else 1024
            peak_memory_mb = (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / memory_divisor
            )
            duration_seconds = time.perf_counter() - started
            if metrics is not None:
                metrics["processing_time_seconds"] = round(duration_seconds, 3)
                metrics["memory_peak_mb"] = round(peak_memory_mb, 2)
            model_run.eval_metrics = metrics
            model_run.status = "ready"
            model_run.finished_at = datetime.now(timezone.utc)
            job.status = "completed"
            job.progress = 100
            job.message = (
                f"Completed: {len(scored)} windows scored, {len(alerts)} alerts created."
            )
            job.result = {
                "model_run_id": model_run.id,
                "scored_windows": len(scored),
                "alerts_created": len(alerts),
                "has_evaluation_metrics": metrics is not None,
                "processing_time_seconds": round(duration_seconds, 3),
            }
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job is not None:
                job.status = "failed"
                job.message = str(exc)
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
            logger.exception("Detection job %s failed", job_id)
