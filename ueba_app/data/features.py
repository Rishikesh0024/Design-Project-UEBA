"""
ueba_app/data/features.py
--------------------------
Extracts per-user daily behavioural features from the cleaned event log.

Performance notes
-----------------
* All aggregation is done with a single vectorised groupby + agg call.
* No Python-level row iteration anywhere in the hot path.
* Baseline deviation attachment uses map() + vectorised arithmetic.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("ueba.features")

MIN_HISTORY_DAYS = 7
AFTER_HOURS_START = 18   # >= this hour is after-hours
AFTER_HOURS_END   = 8    # <  this hour is after-hours

FEATURE_COLS = [
    "total_events",
    "logon_count",
    "file_count",
    "email_count",
    "web_count",
    "device_count",
    "after_hours_count",
    "distinct_pcs",
    "distinct_resources",
    "new_resources",
    "after_hours_ratio",
    "file_ratio",
    "web_ratio",
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_features(
    df: pd.DataFrame,
    users_df: Optional[pd.DataFrame] = None,
    train_end_date: Optional[date] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date

    all_dates = sorted(df["date"].unique())
    if train_end_date is None:
        split_idx      = max(1, int(len(all_dates) * 0.70))
        train_end_date = all_dates[split_idx - 1]

    logger.info("Training window ends: %s", train_end_date)

    # ── Boolean helper columns (vectorised) ───────────────────────────────────
    df["is_after_hours"] = (df["hour"] >= AFTER_HOURS_START) | (df["hour"] < AFTER_HOURS_END)
    df["is_logon"]  = df["activity"] == "logon"
    df["is_file"]   = df["activity"] == "file"
    df["is_email"]  = df["activity"] == "email"
    df["is_web"]    = df["activity"] == "web"
    df["is_device"] = df["activity"] == "device"
    df["res_clean"] = df["resource"].where(df["resource"] != "", other=pd.NA)
    df["pc_clean"]  = df["pc"].where(df["pc"] != "", other=pd.NA)

    # ── Known resources per user from training window only ────────────────────
    train_mask = df["date"] <= train_end_date
    known_res: dict[str, set] = (
        df[train_mask & df["res_clean"].notna()]
        .groupby("user")["res_clean"]
        .apply(set)
        .to_dict()
    )

    # ── Vectorised daily aggregation ──────────────────────────────────────────
    grp = df.groupby(["user", "date"])

    daily = pd.DataFrame({
        "total_events":      grp.size(),
        "logon_count":       grp["is_logon"].sum(),
        "file_count":        grp["is_file"].sum(),
        "email_count":       grp["is_email"].sum(),
        "web_count":         grp["is_web"].sum(),
        "device_count":      grp["is_device"].sum(),
        "after_hours_count": grp["is_after_hours"].sum(),
        "distinct_pcs":      grp["pc_clean"].nunique(),
        "distinct_resources":grp["res_clean"].nunique(),
        "label":             grp["label"].max(),
    }).reset_index()

    # Ratio columns (vectorised)
    daily["after_hours_ratio"] = (
        daily["after_hours_count"] / daily["total_events"].clip(lower=1)
    ).round(4)
    daily["file_ratio"] = (
        daily["file_count"] / daily["total_events"].clip(lower=1)
    ).round(4)
    daily["web_ratio"] = (
        daily["web_count"] / daily["total_events"].clip(lower=1)
    ).round(4)

    daily["in_train"] = daily["date"] <= train_end_date

    # ── New resources (only for eval window, vectorised per row) ──────────────
    # Build a lookup: for each (user, date) in eval window count unseen resources
    eval_df = df[~train_mask & df["res_clean"].notna()][["user", "date", "res_clean"]].copy()
    if len(eval_df) > 0:
        def _count_new(sub):
            user = sub.name[0]
            known = known_res.get(user, set())
            return len(set(sub["res_clean"]) - known)

        new_res_series = (
            eval_df.groupby(["user", "date"])
            .apply(_count_new)
            .rename("new_resources")
            .reset_index()
        )
        daily = daily.merge(new_res_series, on=["user", "date"], how="left")
        daily["new_resources"] = daily["new_resources"].fillna(0).astype(int)
    else:
        daily["new_resources"] = 0

    # ── Baselines & deviations ────────────────────────────────────────────────
    baselines = _compute_baselines(daily, users_df)
    daily     = _attach_deviations(daily, baselines)

    return daily, baselines


# ─────────────────────────────────────────────────────────────────────────────
# Baselines
# ─────────────────────────────────────────────────────────────────────────────

def _mad(series: pd.Series) -> float:
    med = series.median()
    return float((series - med).abs().median())


def _stats_for_group(grp: pd.DataFrame) -> dict:
    stats: dict = {}
    for col in FEATURE_COLS:
        if col not in grp.columns:
            continue
        med = grp[col].median()
        mad = _mad(grp[col])
        stats[f"{col}_median"] = round(float(med), 4)
        stats[f"{col}_mad"]    = round(float(mad), 4)
    return stats


def _compute_baselines(
    daily: pd.DataFrame,
    users_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    train = daily[daily["in_train"]]

    role_map: dict[str, str] = {}
    if users_df is not None and "user_id" in users_df.columns and "role" in users_df.columns:
        role_map = dict(zip(users_df["user_id"], users_df["role"]))

    global_stats = _stats_for_group(train)

    role_stats: dict[str, dict] = {}
    if role_map:
        tw = train.copy()
        tw["role"] = tw["user"].map(role_map)
        for role, grp in tw.groupby("role"):
            role_stats[role] = _stats_for_group(grp)

    rows = []
    for user, grp in train.groupby("user"):
        if len(grp) >= MIN_HISTORY_DAYS:
            stats  = _stats_for_group(grp)
            source = "individual"
        else:
            role = role_map.get(user)
            if role and role in role_stats:
                stats  = role_stats[role]
                source = f"role:{role}"
            else:
                stats  = global_stats
                source = "global"
        rows.append({"user": user, "baseline_source": source, **stats})

    return pd.DataFrame(rows)


def _attach_deviations(daily: pd.DataFrame, baselines: pd.DataFrame) -> pd.DataFrame:
    bl  = baselines.set_index("user")
    eps = 1e-6

    for col in FEATURE_COLS:
        med_col = f"{col}_median"
        mad_col = f"{col}_mad"
        if med_col not in bl.columns or col not in daily.columns:
            continue
        medians = daily["user"].map(bl[med_col]).fillna(bl[med_col].mean())
        mads    = daily["user"].map(bl[mad_col]).fillna(bl[mad_col].mean())
        daily[f"{col}_dev"] = (
            (daily[col] - medians) / (mads + eps)
        ).clip(-10, 10).round(4)

    return daily
