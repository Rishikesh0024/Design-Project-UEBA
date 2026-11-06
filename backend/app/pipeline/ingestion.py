"""
Data ingestion pipeline.

Responsibilities:
- Accept a CSV file path and an optional column mapping.
- Validate required columns, parse timestamps, normalise values.
- Persist ActivityEvent rows and update Dataset statistics.
- Never silently discard records; every skip is logged with a reason.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.db.models import ActivityEvent, Dataset, UserProfile

logger = logging.getLogger("ueba.ingestion")

# ---------------------------------------------------------------------------
# Default column-name aliases  (canonical_name -> list of accepted aliases)
# ---------------------------------------------------------------------------
DEFAULT_ALIASES: dict[str, list[str]] = {
    "id":         ["id", "event_id", "eventid", "log_id"],
    "user":       ["user", "user_id", "userid", "username", "employee"],
    "timestamp":  ["timestamp", "date", "datetime", "time", "event_time", "date/time"],
    "event_type": ["event_type", "activity", "type", "action", "event"],
    "pc":         ["pc", "computer", "host", "machine", "device", "hostname"],
    "resource":   ["resource", "file", "url", "email_to", "to", "filename", "path"],
    "activity":   ["activity", "detail", "details", "description"],
}

REQUIRED_CANONICAL = {"user", "timestamp", "event_type"}

EVENT_TYPE_MAP: dict[str, str] = {
    # logon variants
    "logon": "logon", "login": "logon", "log on": "logon",
    "logoff": "logoff", "logout": "logoff", "log off": "logoff",
    # file
    "file": "file", "file access": "file", "fileaccess": "file",
    # email
    "email": "email", "mail": "email",
    # web
    "web": "web", "http": "web", "browse": "web", "www": "web",
    # device
    "device": "device", "removable": "device", "usb": "device",
    "removable media": "device",
}


def _resolve_column_mapping(
    df_columns: list[str],
    user_mapping: dict[str, str] | None,
) -> dict[str, str]:
    """
    Return {canonical_name: actual_df_column}.
    user_mapping overrides auto-detection.
    """
    lower_cols = {c.lower().strip(): c for c in df_columns}
    resolved: dict[str, str] = {}

    for canonical, aliases in DEFAULT_ALIASES.items():
        if user_mapping and canonical in user_mapping:
            resolved[canonical] = user_mapping[canonical]
            continue
        for alias in aliases:
            if alias in lower_cols:
                resolved[canonical] = lower_cols[alias]
                break

    return resolved


def _parse_timestamp(value: Any) -> datetime | None:
    if pd.isna(value):
        return None
    s = str(value).strip()
    formats = [
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, utc=True).to_pydatetime()
    except Exception:
        return None


def _normalise_event_type(raw: str) -> str:
    key = str(raw).lower().strip()
    return EVENT_TYPE_MAP.get(key, key)


def ingest_dataset(
    db: Session,
    dataset: Dataset,
    file_path: Path,
    user_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Parse CSV, validate, persist events.
    Returns an ingestion summary dict.
    """
    skipped: list[dict[str, Any]] = []
    inserted = 0

    # ---- Read CSV --------------------------------------------------------
    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False, low_memory=False)
    except Exception as exc:
        msg = f"Failed to read CSV: {exc}"
        logger.error(msg)
        dataset.status = "error"
        dataset.error_summary = msg
        db.commit()
        return {"error": msg, "inserted": 0, "skipped": []}

    df.columns = [c.strip() for c in df.columns]
    total_rows = len(df)
    dataset.total_rows = total_rows

    # ---- Resolve column mapping ------------------------------------------
    col_map = _resolve_column_mapping(list(df.columns), user_mapping)
    missing = REQUIRED_CANONICAL - set(col_map.keys())
    if missing:
        msg = f"Required columns not found: {missing}. Available: {list(df.columns)}"
        logger.error(msg)
        dataset.status = "error"
        dataset.error_summary = msg
        db.commit()
        return {"error": msg, "inserted": 0, "skipped": []}

    # Persist resolved mapping
    dataset.column_mapping = json.dumps(col_map)

    # ---- Process rows ----------------------------------------------------
    users_seen: set[str] = set()

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # 1-based, header is row 1

        user_val = str(row.get(col_map["user"], "")).strip()
        if not user_val:
            skipped.append({"row": row_num, "reason": "empty user field"})
            continue

        ts_raw = row.get(col_map["timestamp"], "")
        ts = _parse_timestamp(ts_raw)
        if ts is None:
            skipped.append({"row": row_num, "reason": f"unparseable timestamp: {ts_raw!r}"})
            continue

        event_type_raw = str(row.get(col_map["event_type"], "")).strip()
        event_type = _normalise_event_type(event_type_raw)

        original_id = str(row.get(col_map.get("id", ""), "")).strip() or None
        pc = str(row.get(col_map.get("pc", ""), "")).strip() or None
        resource = str(row.get(col_map.get("resource", ""), "")).strip() or None
        activity = str(row.get(col_map.get("activity", ""), "")).strip() or None

        raw_json = json.dumps(row.to_dict())

        event = ActivityEvent(
            dataset_id=dataset.id,
            original_id=original_id,
            user_id=user_val,
            event_type=event_type,
            timestamp=ts.isoformat(),
            day_of_week=ts.weekday(),
            hour_of_day=ts.hour,
            pc=pc,
            resource=resource,
            activity=activity,
            raw_json=raw_json,
        )
        db.add(event)
        users_seen.add(user_val)
        inserted += 1

        # Batch commit every 5000 rows to avoid huge transactions
        if inserted % 5000 == 0:
            db.commit()
            logger.info("Ingested %d rows so far…", inserted)

    db.commit()

    # ---- Upsert UserProfile stubs ----------------------------------------
    for uid in users_seen:
        existing = db.query(UserProfile).filter_by(user_id=uid).first()
        if not existing:
            db.add(UserProfile(user_id=uid))
    db.commit()

    # ---- Update dataset stats --------------------------------------------
    dataset.valid_rows = inserted
    dataset.skipped_rows = len(skipped)
    dataset.status = "ready"
    if skipped:
        dataset.error_summary = json.dumps(skipped[:200])  # cap stored summary
    db.commit()

    summary = {
        "total_rows": total_rows,
        "inserted": inserted,
        "skipped_count": len(skipped),
        "skipped_sample": skipped[:20],
        "users_found": len(users_seen),
        "column_mapping": col_map,
    }
    logger.info("Ingestion complete: %s", summary)
    return summary
