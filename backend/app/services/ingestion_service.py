from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models_db.models import ActivityEvent, Dataset, UserProfile

logger = logging.getLogger(__name__)

ALIASES = {
    "event_id": ("id", "event_id", "eventid", "log_id"),
    "timestamp": ("date", "timestamp", "datetime", "time", "event_time"),
    "user": ("user", "user_id", "userid", "username", "employee"),
    "activity": ("activity", "event_type", "type", "action", "event"),
    "pc": ("pc", "computer", "host", "machine", "hostname"),
    "resource": ("resource", "file", "filename", "url", "to", "email_to", "path"),
    "role": ("role", "job_role"),
    "department": ("department", "dept"),
    "label": ("label", "ground_truth", "is_anomaly", "malicious"),
}
EVENT_TYPES = {
    "logon": "logon", "login": "logon", "log off": "logoff", "logoff": "logoff",
    "logout": "logoff", "file": "file", "email": "email", "http": "web",
    "web": "web", "www": "web", "device": "device", "removable": "device",
    "removable device": "device", "usb": "device",
}
FILE_TYPES = {
    "logon": "logon", "file": "file", "email": "email",
    "http": "web", "web": "web", "device": "device",
}


def _column_map(columns: list[str]) -> dict[str, str]:
    by_name = {column.strip().lower(): column for column in columns}
    return {
        canonical: by_name[alias]
        for canonical, aliases in ALIASES.items()
        for alias in aliases
        if alias in by_name
    }


def _normalize_activity(value: object, path: Path) -> str:
    source = str(value or "").strip().lower()
    stem = path.stem.lower().split("_", 1)[-1]
    file_type = FILE_TYPES.get(stem)
    return file_type or EVENT_TYPES.get(source, source or "unknown")


def _load_csv(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame.columns = [column.strip() for column in frame.columns]
    return frame, _column_map(list(frame.columns))


def ingest_dataset(dataset_id: int) -> None:
    """Validate uploaded CERT CSV files and persist normalized events and roles."""
    with SessionLocal() as db:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None:
            logger.error("Ingestion requested for missing dataset %s", dataset_id)
            return

        dataset.status = "processing"
        db.commit()
        try:
            source = Path(dataset.file_path)
            files = sorted(source.glob("*.csv")) if source.is_dir() else [source]
            if not files:
                raise ValueError("No CSV files were found in the uploaded dataset.")

            total_rows = 0
            role_metadata_rows = 0
            skipped_rows = 0
            duplicate_rows = 0
            role_metadata: dict[str, tuple[str | None, str | None]] = {}
            pending_events: list[dict] = []
            columns_seen: dict[str, list[str]] = {}
            missing_values: dict[str, int] = {}
            has_labels = False

            for path in files:
                frame, columns = _load_csv(path)
                columns_seen[path.name] = list(frame.columns)
                for column in frame.columns:
                    empty_count = int(frame[column].astype(str).str.strip().eq("").sum())
                    missing_values[column] = missing_values.get(column, 0) + empty_count
                if "user" not in columns:
                    total_rows += len(frame)
                    logger.info("Skipping non-event file without a user column: %s", path.name)
                    continue
                if "timestamp" not in columns:
                    if "role" in columns:
                        role_metadata_rows += len(frame)
                        for _, row in frame.iterrows():
                            user_id = str(row[columns["user"]]).strip()
                            if user_id:
                                role_metadata[user_id] = (
                                    str(row[columns["role"]]).strip() or None,
                                    str(row[columns["department"]]).strip()
                                    if "department" in columns else None,
                                )
                        columns_seen[path.name] = list(frame.columns)
                        continue
                    total_rows += len(frame)
                    raise ValueError(
                        f"{path.name} has no timestamp column and is not role metadata."
                    )

                total_rows += len(frame)

                timestamps = pd.to_datetime(
                    frame[columns["timestamp"]], utc=True, errors="coerce"
                )
                users = frame[columns["user"]].astype(str).str.strip()
                valid = timestamps.notna() & users.ne("")
                skipped_rows += int((~valid).sum())
                if "label" in columns:
                    has_labels = True

                candidate = pd.DataFrame({
                    "user": users[valid],
                    "timestamp": timestamps[valid],
                    "activity": (
                        frame.loc[valid, columns["activity"]]
                        if "activity" in columns else ""
                    ),
                    "pc": frame.loc[valid, columns["pc"]]
                    if "pc" in columns else "",
                    "resource": frame.loc[valid, columns["resource"]]
                    if "resource" in columns else "",
                    "event_id": frame.loc[valid, columns["event_id"]]
                    if "event_id" in columns else "",
                    "label": pd.to_numeric(
                        frame.loc[valid, columns["label"]], errors="coerce"
                    ).fillna(0).clip(0, 1).astype(int)
                    if "label" in columns else 0,
                })
                candidate["activity"] = candidate["activity"].map(
                    lambda value: _normalize_activity(value, path)
                )
                candidate["event_id"] = candidate["event_id"].where(
                    candidate["event_id"].astype(str).str.strip().ne(""),
                    other=None,
                )
                candidate["event_id"] = candidate["event_id"].fillna(
                    pd.Series(
                        [f"{path.stem}-{index + 1}" for index in candidate.index],
                        index=candidate.index,
                    )
                )
                duplicate_rows += int(candidate.duplicated(
                    subset=["event_id"] if columns.get("event_id")
                    else ["user", "timestamp", "activity", "resource", "pc"]
                ).sum())
                pending_events.extend(candidate.to_dict(orient="records"))

                if "role" in columns:
                    for _, row in frame.iterrows():
                        user_id = str(row[columns["user"]]).strip()
                        if user_id:
                            role_metadata[user_id] = (
                                str(row[columns["role"]]).strip() or None,
                                str(row[columns["department"]]).strip()
                                if "department" in columns else None,
                            )

            if not pending_events:
                raise ValueError("No valid activity events were found in the uploaded CSV files.")

            event_objects = []
            for record in pending_events:
                timestamp = record["timestamp"].to_pydatetime()
                event_objects.append(ActivityEvent(
                    dataset_id=dataset_id,
                    event_id=str(record["event_id"])[:100],
                    user_id=str(record["user"])[:100],
                    activity=str(record["activity"])[:50],
                    timestamp=timestamp,
                    pc=str(record["pc"])[:200] or None,
                    resource=str(record["resource"])[:1024] or None,
                    label=int(record["label"]),
                    hour=timestamp.hour,
                    day_of_week=timestamp.weekday(),
                ))
            db.add_all(event_objects)

            grouped_users: dict[str, list[ActivityEvent]] = {}
            for event in event_objects:
                grouped_users.setdefault(event.user_id, []).append(event)
            for user_id, user_events in grouped_users.items():
                existing = db.scalar(select(UserProfile).where(
                    UserProfile.dataset_id == dataset_id,
                    UserProfile.user_id == user_id,
                ))
                timestamps = [event.timestamp for event in user_events]
                role, department = role_metadata.get(user_id, (None, None))
                profile = existing or UserProfile(
                    dataset_id=dataset_id, user_id=user_id
                )
                profile.role = role or profile.role
                profile.department = department or profile.department
                profile.total_events = len(user_events)
                profile.active_days = len({event.timestamp.date() for event in user_events})
                profile.last_activity = max(timestamps)
                db.add(profile)

            all_timestamps = [event.timestamp for event in event_objects]
            dataset.total_rows = total_rows
            dataset.valid_rows = len(event_objects)
            dataset.unique_users = len(grouped_users)
            dataset.date_from = min(all_timestamps).date().isoformat()
            dataset.date_to = max(all_timestamps).date().isoformat()
            dataset.has_labels = has_labels
            source_metadata = (
                dataset.schema_info if isinstance(dataset.schema_info, dict) else {}
            )
            dataset.schema_info = {
                **source_metadata,
                "files": columns_seen,
                "event_types": sorted({event.activity for event in event_objects}),
                "role_metadata_users": len(role_metadata),
                "role_metadata_rows": role_metadata_rows,
            }
            dataset.quality_report = {
                "record_count": total_rows,
                "valid_records": len(event_objects),
                "missing_or_invalid_records": skipped_rows,
                "duplicate_records": duplicate_rows,
                "unique_users": len(grouped_users),
                "missing_values": missing_values,
            }
            dataset.status = "ready"
            db.commit()
        except Exception as exc:
            db.rollback()
            dataset = db.get(Dataset, dataset_id)
            if dataset is not None:
                dataset.status = "failed"
                dataset.quality_report = {"error": str(exc)}
                db.commit()
            logger.exception("Dataset ingestion failed for dataset %s", dataset_id)
