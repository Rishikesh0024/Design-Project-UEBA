"""
ueba_app/data/loader.py
-----------------------
Loads a CSV activity log, validates required columns, parses timestamps,
and returns a clean DataFrame plus an ingestion summary.

Column-mapping layer
--------------------
The CERT dataset releases use different column names across versions.
We resolve aliases to canonical names so the rest of the pipeline is
schema-agnostic.

Canonical columns produced
--------------------------
  event_id   – original event identifier (or auto-generated)
  timestamp  – UTC-aware datetime
  user       – user identifier string
  activity   – normalised event type  (logon|logoff|file|email|web|device)
  pc         – workstation identifier (optional)
  resource   – file path / URL / email address (optional)
  label      – ground-truth anomaly label 0/1 (optional, kept if present)
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

import pandas as pd

logger = logging.getLogger("ueba.loader")

# ── Column-name aliases ───────────────────────────────────────────────────────
_ALIASES: dict[str, list[str]] = {
    "event_id":  ["id", "event_id", "eventid", "log_id", "index"],
    "timestamp": ["date", "timestamp", "datetime", "time", "event_time", "date/time"],
    "user":      ["user", "user_id", "userid", "username", "employee"],
    "activity":  ["activity", "event_type", "type", "action", "event"],
    "pc":        ["pc", "computer", "host", "machine", "device", "hostname"],
    "resource":  ["resource", "file", "url", "to", "filename", "path", "email_to"],
    "label":     ["label", "ground_truth", "is_anomaly", "malicious"],
}

REQUIRED_CANONICAL = {"timestamp", "user", "activity"}

# ── Event-type normalisation map ─────────────────────────────────────────────
_EVENT_MAP: dict[str, str] = {
    "logon": "logon", "login": "logon", "log on": "logon",
    "logoff": "logoff", "logout": "logoff", "log off": "logoff",
    "file": "file", "file access": "file", "fileaccess": "file",
    "email": "email", "mail": "email",
    "www": "web", "web": "web", "http": "web", "browse": "web",
    "device": "device", "removable": "device", "usb": "device",
    "removable media": "device",
}

# ── Timestamp formats tried in order ─────────────────────────────────────────
_TS_FORMATS = [
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d",
]


# ─────────────────────────────────────────────────────────────────────────────

def _resolve_mapping(columns: list[str]) -> dict[str, str]:
    """Return {canonical: actual_column} using alias matching."""
    lower = {c.lower().strip(): c for c in columns}
    resolved: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in lower:
                resolved[canonical] = lower[alias]
                break
    return resolved


def _parse_ts_series(series: pd.Series) -> tuple[pd.Series, list[int]]:
    """
    Parse a string series to UTC-aware datetime.
    Returns (parsed_series, list_of_failed_indices).
    """
    parsed = pd.Series([pd.NaT] * len(series), dtype="object")
    failed: list[int] = []

    for fmt in _TS_FORMATS:
        mask = parsed.isna() & series.notna()
        if not mask.any():
            break
        try:
            attempt = pd.to_datetime(series[mask], format=fmt, utc=True, errors="coerce")
            parsed[mask] = attempt
        except Exception:
            pass

    # Final fallback: pandas inference
    still_na = parsed.isna() & series.notna()
    if still_na.any():
        attempt = pd.to_datetime(series[still_na], utc=True, errors="coerce")
        parsed[still_na] = attempt

    failed = list(parsed[parsed.isna()].index)
    return pd.to_datetime(parsed, utc=True, errors="coerce"), failed


def load_csv(
    source: Union[str, Path, io.BytesIO],
    user_mapping: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Load and validate a CSV activity log.

    Parameters
    ----------
    source       : file path or BytesIO (from Streamlit uploader)
    user_mapping : optional override {canonical: actual_column}

    Returns
    -------
    df      : cleaned DataFrame with canonical columns
    summary : ingestion statistics dict
    """
    skipped_rows: list[dict] = []

    # ── Read raw CSV ──────────────────────────────────────────────────────────
    try:
        raw = pd.read_csv(source, dtype=str, keep_default_na=False, low_memory=False)
    except Exception as exc:
        raise ValueError(f"Cannot read CSV: {exc}") from exc

    raw.columns = [c.strip() for c in raw.columns]
    total_rows = len(raw)

    # ── Resolve column mapping ────────────────────────────────────────────────
    col_map = _resolve_mapping(list(raw.columns))
    if user_mapping:
        col_map.update(user_mapping)

    missing = REQUIRED_CANONICAL - set(col_map.keys())
    if missing:
        raise ValueError(
            f"Required columns not found: {missing}. "
            f"Available columns: {list(raw.columns)}"
        )

    # ── Build working frame with canonical names ──────────────────────────────
    df = pd.DataFrame()
    df["event_id"] = (
        raw[col_map["event_id"]] if "event_id" in col_map
        else pd.Series([f"E{i+1:07d}" for i in range(total_rows)])
    )
    df["user"]     = raw[col_map["user"]].str.strip()
    df["activity"] = raw[col_map["activity"]].str.strip()
    df["pc"]       = raw[col_map["pc"]].str.strip() if "pc" in col_map else ""
    df["resource"] = raw[col_map["resource"]].str.strip() if "resource" in col_map else ""
    df["label"]    = (
        pd.to_numeric(raw[col_map["label"]], errors="coerce").fillna(0).astype(int)
        if "label" in col_map else 0
    )

    # ── Parse timestamps ──────────────────────────────────────────────────────
    ts_series, ts_failed = _parse_ts_series(raw[col_map["timestamp"]])
    df["timestamp"] = ts_series

    for idx in ts_failed:
        skipped_rows.append({
            "row": idx + 2,
            "reason": f"unparseable timestamp: {raw[col_map['timestamp']].iloc[idx]!r}",
        })

    # ── Drop rows with empty user or failed timestamp ─────────────────────────
    empty_user_mask = df["user"].eq("")
    for idx in df[empty_user_mask].index:
        skipped_rows.append({"row": int(idx) + 2, "reason": "empty user field"})

    valid_mask = df["timestamp"].notna() & ~empty_user_mask
    df = df[valid_mask].copy()

    # ── Normalise event types ─────────────────────────────────────────────────
    df["activity"] = (
        df["activity"].str.lower().str.strip()
        .map(lambda x: _EVENT_MAP.get(x, x))
    )

    # ── Sort chronologically ──────────────────────────────────────────────────
    df = df.sort_values("timestamp").reset_index(drop=True)

    # ── Derived time columns ──────────────────────────────────────────────────
    df["date"]        = df["timestamp"].dt.date
    df["hour"]        = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.day_of_week  # 0=Mon

    summary = {
        "total_rows":    total_rows,
        "valid_rows":    len(df),
        "skipped_count": len(skipped_rows),
        "skipped_sample": skipped_rows[:20],
        "unique_users":  df["user"].nunique(),
        "date_range":    (
            str(df["timestamp"].min().date()),
            str(df["timestamp"].max().date()),
        ),
        "event_types":   df["activity"].value_counts().to_dict(),
        "column_mapping": col_map,
        "has_labels":    bool((df["label"] == 1).any()),
    }

    logger.info(
        "Loaded %d valid rows (%d skipped) | %d users | %s → %s",
        len(df), len(skipped_rows),
        summary["unique_users"], *summary["date_range"],
    )
    return df, summary
