"""
ueba_app/models/scorer.py
--------------------------
Converts anomaly scores into a transparent 0–100 risk score,
assigns severity categories, and generates human-readable explanations.

Risk score formula (documented)
--------------------------------
  risk = 100 × (w_if × if_score + w_stat × stat_score + w_rule × rule_norm)
  where rule_norm = n_rule_flags / total_rules

Weights are configurable; defaults sum to 1.0.

Severity thresholds (configurable)
------------------------------------
  Critical : risk ≥ 75
  High     : risk ≥ 50
  Medium   : risk ≥ 25
  Low      : risk < 25

IMPORTANT: Risk score is a prioritization ranking, NOT a calibrated
probability of malicious intent.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger("ueba.scorer")

DEFAULT_WEIGHTS = {
    "w_if":   0.45,
    "w_stat": 0.35,
    "w_rule": 0.20,
}

DEFAULT_THRESHOLDS = {
    "critical": 75,
    "high":     50,
    "medium":   25,
}

_FEATURE_LABELS = {
    "total_events":       "total activity volume",
    "logon_count":        "logon frequency",
    "file_count":         "file-access volume",
    "email_count":        "email activity",
    "web_count":          "web activity",
    "device_count":       "removable-device usage",
    "after_hours_count":  "after-hours activity count",
    "after_hours_ratio":  "proportion of after-hours activity",
    "distinct_resources": "number of distinct resources accessed",
    "new_resources":      "number of previously unseen resources",
}

_RULE_LABELS = {
    "high_after_hours_ratio": "activity predominantly outside working hours",
    "high_device_usage":      "unusually high removable-device usage",
    "new_resources_accessed": "access to previously unseen resources",
    "file_volume_spike":      "file-access volume substantially above baseline",
    "web_volume_spike":       "web activity substantially above baseline",
}


# ─────────────────────────────────────────────────────────────────────────────

def compute_risk_scores(
    scored: pd.DataFrame,
    weights: dict | None = None,
    thresholds: dict | None = None,
    total_rules: int = 5,
) -> pd.DataFrame:
    """
    Add risk_score (0–100) and severity columns to the scored DataFrame.
    """
    w  = {**DEFAULT_WEIGHTS,    **(weights    or {})}
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    rule_norm = (scored["n_rule_flags"] / max(total_rules, 1)).clip(0, 1)

    risk = 100.0 * (
        w["w_if"]   * scored["if_score"]
        + w["w_stat"] * scored["stat_score"]
        + w["w_rule"] * rule_norm
    )
    scored = scored.copy()
    scored["risk_score"] = risk.clip(0, 100).round(1)
    scored["severity"]   = scored["risk_score"].apply(
        lambda s: _assign_severity(s, th)
    )
    return scored


def _assign_severity(score: float, th: dict) -> str:
    if score >= th["critical"]:
        return "Critical"
    if score >= th["high"]:
        return "High"
    if score >= th["medium"]:
        return "Medium"
    return "Low"


# ─────────────────────────────────────────────────────────────────────────────

def generate_alerts(
    scored: pd.DataFrame,
    events_df: pd.DataFrame,
    baselines: pd.DataFrame,
    min_risk: float = 25.0,
) -> pd.DataFrame:
    anomalies = scored[scored["is_anomaly"] & (scored["risk_score"] >= min_risk)].copy()
    anomalies = anomalies.sort_values("risk_score", ascending=False).reset_index(drop=True)

    bl = baselines.set_index("user")
    records = []

    # Pre-build a (user, date_str) -> [event_ids] lookup once — O(n_events)
    events_df = events_df.copy()
    events_df["date_str"] = events_df["date"].astype(str)
    event_lookup: dict[tuple, list] = {}
    for row in events_df[["user", "date_str", "event_id"]].itertuples(index=False):
        key = (row.user, row.date_str)
        if key not in event_lookup:
            event_lookup[key] = []
        event_lookup[key].append(row.event_id)

    for _, row in anomalies.iterrows():
        user = row["user"]
        day  = str(row["date"])

        event_ids = event_lookup.get((user, day), [])
        deviations = _top_deviations(row, bl.get(user) if user in bl.index else None)
        explanation = _build_explanation(row, deviations)

        rule_score = round(float(row["n_rule_flags"]) / 5.0, 3)  # normalised 0-1 over 5 rules
        records.append({
            "alert_id":              f"ALT-{len(records)+1:04d}",
            "user":                  user,
            "date":                  day,
            "primary_activity":      _dominant_activity(row),
            "risk_score":            row["risk_score"],
            "severity":              row["severity"],
            "if_score":              round(float(row["if_score"]), 3),
            "stat_score":            round(float(row["stat_score"]), 3),
            "rule_score":            rule_score,
            "rule_flags":            row["rule_flags"],
            "n_rule_flags":          int(row["n_rule_flags"]),
            "explanation":           explanation,
            "supporting_event_ids": event_ids[:50],
            "n_supporting_events":  len(event_ids),
            "label":                int(row.get("label", 0)),
            "status":               "open",
            "verdict":              "",
            "analyst_note":         "",
        })

    alerts = pd.DataFrame(records)
    logger.info("Generated %d alerts (min_risk=%.0f)", len(alerts), min_risk)
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Explanation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _top_deviations(row: pd.Series, user_bl: Any) -> list[tuple[str, float, float, float]]:
    """
    Return list of (feature_label, observed, baseline_median, deviation)
    for the top deviating features.
    """
    results = []
    for feat, label in _FEATURE_LABELS.items():
        dev_col = f"{feat}_dev"
        if dev_col not in row.index:
            continue
        dev = float(row.get(dev_col, 0))
        if dev < 1.5:
            continue
        observed = float(row.get(feat, 0))
        baseline = float(user_bl.get(f"{feat}_median", 0)) if user_bl is not None else 0.0
        results.append((label, observed, baseline, dev))

    results.sort(key=lambda x: x[3], reverse=True)
    return results[:4]


def _build_explanation(row: pd.Series, deviations: list) -> str:
    severity = row["severity"]
    parts = [f"{severity}-priority anomaly detected for user {row['user']} on {row['date']}."]

    if deviations:
        parts.append("Unusual behavioural indicators:")
        for label, obs, base, dev in deviations:
            parts.append(
                f"  • {label.capitalize()}: {obs:.0f} "
                f"(baseline ≈ {base:.1f}, deviation {dev:.1f}×)."
            )

    rule_flags: list = row.get("rule_flags", [])
    if rule_flags:
        parts.append("Triggered detection rules:")
        for flag in rule_flags:
            parts.append(f"  • {_RULE_LABELS.get(flag, flag)}.")

    parts.append(
        "Note: this score reflects prioritization for investigation, "
        "not a confirmed determination of malicious intent."
    )
    return " ".join(parts)


def _dominant_activity(row: pd.Series) -> str:
    counts = {
        "logon":  row.get("logon_count",  0),
        "file":   row.get("file_count",   0),
        "email":  row.get("email_count",  0),
        "web":    row.get("web_count",    0),
        "device": row.get("device_count", 0),
    }
    return max(counts, key=counts.get)
