"""
ueba_app/models/detector.py
----------------------------
Anomaly detection pipeline:
  1. Isolation Forest (scikit-learn) trained on the training window.
  2. Statistical deviation score derived from per-feature MAD deviations.
  3. Rule-based flags as supplementary evidence.

The model is trained ONLY on rows where in_train == True.
Test rows are scored without re-fitting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from ueba_app.data.features import FEATURE_COLS

logger = logging.getLogger("ueba.detector")

MODEL_DIR = Path(__file__).parent.parent.parent / "saved_models"
MODEL_DIR.mkdir(exist_ok=True)

IF_CONTAMINATION = 0.05   # expected fraction of anomalies
IF_N_ESTIMATORS  = 100    # sklearn default; sufficient for this dataset size
IF_RANDOM_STATE  = 42

# Rule thresholds (configurable via settings dict)
DEFAULT_RULES = {
    "after_hours_ratio_threshold": 0.5,   # >50 % of events after hours
    "device_count_threshold":      3,     # ≥3 device events in a day
    "new_resources_threshold":     5,     # ≥5 new resources in a day
    "file_count_dev_threshold":    3.0,   # file_count deviation > 3 MADs
    "web_count_dev_threshold":     3.0,
}

DEV_COLS = [f"{c}_dev" for c in FEATURE_COLS]


# ─────────────────────────────────────────────────────────────────────────────

class UEBADetector:
    """Wraps Isolation Forest + statistical + rule-based detection."""

    def __init__(self, rules: dict | None = None):
        self.rules   = {**DEFAULT_RULES, **(rules or {})}
        self.scaler  = RobustScaler()
        self.model   = IsolationForest(
            n_estimators=IF_N_ESTIMATORS,
            contamination=IF_CONTAMINATION,
            random_state=IF_RANDOM_STATE,
            n_jobs=-1,
        )
        self._fitted = False

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(self, daily: pd.DataFrame) -> None:
        """Fit scaler and Isolation Forest on training rows only."""
        train = daily[daily["in_train"] == True].copy()  # noqa: E712
        if len(train) == 0:
            raise ValueError("No training rows found (in_train == True).")

        X_train = self._get_feature_matrix(train)
        X_scaled = self.scaler.fit_transform(X_train)
        self.model.fit(X_scaled)
        self._fitted = True
        logger.info("IsolationForest fitted on %d training rows.", len(train))

    # ── Scoring ───────────────────────────────────────────────────────────────

    def score(self, daily: pd.DataFrame) -> pd.DataFrame:
        """
        Score all rows (train + eval).
        Adds columns:
          if_score        – raw IF anomaly score (higher = more anomalous, 0–1)
          stat_score      – statistical deviation score (0–1)
          rule_flags      – list of triggered rule names
          n_rule_flags    – count of triggered rules
          anomaly_score   – combined score (0–1)
          is_anomaly      – bool flag
        """
        if not self._fitted:
            raise RuntimeError("Call fit() before score().")

        result = daily.copy()
        X = self._get_feature_matrix(result)
        X_scaled = self.scaler.transform(X)

        # Isolation Forest: decision_function returns negative scores for anomalies
        raw_if = self.model.decision_function(X_scaled)
        # Normalise to [0,1] where 1 = most anomalous
        if_min, if_max = raw_if.min(), raw_if.max()
        if if_max > if_min:
            if_norm = 1.0 - (raw_if - if_min) / (if_max - if_min)
        else:
            if_norm = np.zeros(len(raw_if))
        result["if_score"] = np.round(if_norm, 4)

        # Statistical score: mean of positive deviations across feature devs
        dev_present = [c for c in DEV_COLS if c in result.columns]
        if dev_present:
            pos_devs = result[dev_present].clip(lower=0)
            stat_raw = pos_devs.mean(axis=1)
            s_max = stat_raw.quantile(0.99) or 1.0
            result["stat_score"] = (stat_raw / s_max).clip(0, 1).round(4)
        else:
            result["stat_score"] = 0.0

        # Rule flags — fully vectorised, no row-level apply
        result["rule_flags"]  = self._apply_rules_vectorised(result)
        result["n_rule_flags"] = result["rule_flags"].apply(len)

        # Combined anomaly score: weighted average
        rule_norm = (result["n_rule_flags"] / max(len(self.rules), 1)).clip(0, 1)
        result["anomaly_score"] = (
            0.45 * result["if_score"]
            + 0.35 * result["stat_score"]
            + 0.20 * rule_norm
        ).round(4)

        result["is_anomaly"] = result["anomaly_score"] > 0.45

        logger.info(
            "Scored %d rows | anomalies: %d",
            len(result), result["is_anomaly"].sum(),
        )
        return result

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, name: str = "ueba_model") -> Path:
        path = MODEL_DIR / f"{name}.joblib"
        joblib.dump({"scaler": self.scaler, "model": self.model, "rules": self.rules}, path)
        logger.info("Model saved → %s", path)
        return path

    @classmethod
    def load(cls, name: str = "ueba_model") -> "UEBADetector":
        path = MODEL_DIR / f"{name}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"No saved model at {path}")
        payload = joblib.load(path)
        det = cls(rules=payload["rules"])
        det.scaler  = payload["scaler"]
        det.model   = payload["model"]
        det._fitted = True
        logger.info("Model loaded ← %s", path)
        return det

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in FEATURE_COLS if c in df.columns]
        return df[cols].fillna(0).astype(float)

    def _apply_rules_vectorised(self, df: pd.DataFrame) -> pd.Series:
        """Compute rule flags for all rows at once using boolean masks."""
        r = self.rules

        masks = {
            "high_after_hours_ratio": df.get("after_hours_ratio", pd.Series(0, index=df.index)) > r["after_hours_ratio_threshold"],
            "high_device_usage":      df.get("device_count",      pd.Series(0, index=df.index)) >= r["device_count_threshold"],
            "new_resources_accessed": df.get("new_resources",     pd.Series(0, index=df.index)) >= r["new_resources_threshold"],
            "file_volume_spike":      df.get("file_count_dev",    pd.Series(0, index=df.index)) > r["file_count_dev_threshold"],
            "web_volume_spike":       df.get("web_count_dev",     pd.Series(0, index=df.index)) > r["web_count_dev_threshold"],
        }

        # Build list of triggered rule names per row without apply()
        flag_matrix = pd.DataFrame(masks)
        return flag_matrix.apply(
            lambda row: [name for name, hit in row.items() if hit], axis=1
        )
