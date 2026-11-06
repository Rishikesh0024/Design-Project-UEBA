"""
ueba_app/models/evaluation.py
------------------------------
Computes detection metrics when ground-truth labels are available.

Methodology
-----------
* Labels are at the (user, date) granularity — a window is positive if
  any event in it has label == 1.
* Predictions are derived from is_anomaly (binary) and risk_score
  (for PR-AUC).
* Training rows are excluded from evaluation to prevent leakage.
* If labels are unavailable or all-zero, descriptive statistics are
  returned instead of accuracy metrics.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("ueba.evaluation")


def evaluate(scored: pd.DataFrame) -> dict:
    """
    Parameters
    ----------
    scored : daily feature DataFrame with columns:
             label, is_anomaly, risk_score, in_train

    Returns
    -------
    dict with keys: has_labels, metrics, descriptive, confusion_matrix
    """
    eval_df = scored[~scored["in_train"]].copy()

    if eval_df.empty:
        return {"has_labels": False, "error": "No evaluation rows available."}

    has_labels = "label" in eval_df.columns and eval_df["label"].sum() > 0

    descriptive = _descriptive_stats(eval_df)

    if not has_labels:
        return {
            "has_labels": False,
            "descriptive": descriptive,
            "note": (
                "No ground-truth labels found. "
                "Showing descriptive anomaly statistics only."
            ),
        }

    y_true = eval_df["label"].astype(int).values
    y_pred = eval_df["is_anomaly"].astype(int).values
    y_score = eval_df["risk_score"].values / 100.0

    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)
    fpr       = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    pr_auc = _pr_auc(y_true, y_score)

    metrics = {
        "precision":         round(precision, 4),
        "recall":            round(recall,    4),
        "f1_score":          round(f1,        4),
        "false_positive_rate": round(fpr,     4),
        "pr_auc":            round(pr_auc,    4),
        "true_positives":    tp,
        "false_positives":   fp,
        "true_negatives":    tn,
        "false_negatives":   fn,
        "support_positive":  int(y_true.sum()),
        "support_negative":  int((y_true == 0).sum()),
    }

    confusion = {
        "labels": ["Normal", "Anomaly"],
        "matrix": [[tn, fp], [fn, tp]],
    }

    return {
        "has_labels":       True,
        "metrics":          metrics,
        "descriptive":      descriptive,
        "confusion_matrix": confusion,
    }


def _descriptive_stats(df: pd.DataFrame) -> dict:
    return {
        "total_windows":    len(df),
        "anomalies_flagged": int(df["is_anomaly"].sum()),
        "anomaly_rate":     round(float(df["is_anomaly"].mean()), 4),
        "risk_score_mean":  round(float(df["risk_score"].mean()), 2),
        "risk_score_p95":   round(float(df["risk_score"].quantile(0.95)), 2),
        "severity_counts":  df["severity"].value_counts().to_dict() if "severity" in df.columns else {},
    }


def _pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Compute area under precision-recall curve via trapezoidal rule."""
    try:
        from sklearn.metrics import average_precision_score
        return float(average_precision_score(y_true, y_score))
    except Exception:
        return 0.0
