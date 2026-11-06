"""Reproducible, explicitly synthetic datasets for the UEBA demo workflow."""
from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


DEMO_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "key": "cert-activity",
        "name": "CERT Activity Demo Dataset",
        "description": "A synthetic CERT-shaped activity stream covering common workplace event types.",
        "seed": 4201,
        "scenario_user": "demo.user.07",
        "suspicious_count": 8,
    },
    {
        "key": "user-behaviour",
        "name": "User Behaviour Demo Dataset",
        "description": "Synthetic user profiles with role-specific routines and a correlated suspicious sequence.",
        "seed": 6202,
        "scenario_user": "demo.user.06",
        "suspicious_count": 10,
    },
    {
        "key": "ueba-threat-scenario",
        "name": "UEBA Threat Scenario Dataset",
        "description": "A synthetic, labelled scenario with unusual logins, file access, data transfer, and removable-device activity.",
        "seed": 8803,
        "scenario_user": "demo.user.08",
        "suspicious_count": 14,
    },
)

USER_ROLES = (
    ("Engineering", "Technology"),
    ("Finance", "Corporate"),
    ("Human Resources", "Corporate"),
    ("IT Operations", "Technology"),
    ("Legal", "Corporate"),
    ("Sales", "Commercial"),
    ("Research", "Technology"),
    ("Executive", "Leadership"),
)

EVENT_COLUMNS = (
    "event_id",
    "timestamp",
    "user_id",
    "activity",
    "pc",
    "resource",
    "role",
    "department",
    "label",
)
COLUMN_TYPES = {
    "event_id": "string",
    "timestamp": "datetime (ISO-8601 UTC)",
    "user_id": "string",
    "activity": "category",
    "pc": "string (device ID)",
    "resource": "string",
    "role": "category",
    "department": "category",
    "label": "integer (binary ground truth)",
}


def generate_demo_records(dataset_key: str) -> list[dict[str, Any]]:
    """Return a stable synthetic event stream sorted by timestamp and event ID."""
    spec = next((item for item in DEMO_CATALOG if item["key"] == dataset_key), None)
    if spec is None:
        raise ValueError(f"Unknown demo dataset: {dataset_key}")

    rng = random.Random(spec["seed"])
    start = datetime(2025, 2, 3, tzinfo=timezone.utc)
    records: list[dict[str, Any]] = []
    sequence = 0

    for day in range(7):
        for user_index, (role, department) in enumerate(USER_ROLES, start=1):
            user_id = f"demo.user.{user_index:02d}"
            pc = f"DEMO-PC-{(user_index + day) % 6 + 1:02d}"
            activities = ("logon", "file", "email", "web", "device")
            for activity_index, activity in enumerate(activities):
                sequence += 1
                event_time = start + timedelta(
                    days=day,
                    hours=8 + activity_index * 2 + rng.randrange(0, 2),
                    minutes=rng.randrange(0, 60),
                )
                records.append({
                    "event_id": f"DEMO-{spec['seed']}-{sequence:05d}",
                    "timestamp": event_time.isoformat(),
                    "user_id": user_id,
                    "activity": activity,
                    "pc": pc,
                    "resource": _normal_resource(activity, user_index, day, rng),
                    "role": role,
                    "department": department,
                    "label": 0,
                })

    scenario_user = str(spec["scenario_user"])
    role, department = USER_ROLES[int(scenario_user[-2:]) - 1]
    scenario = (
        ("logon", 1, "off-hours sign-in from an unfamiliar workstation"),
        ("file", 2, "access to a restricted archive"),
        ("file", 3, "bulk access to sensitive records"),
        ("web", 4, "upload to an external transfer destination"),
        ("device", 5, "removable storage connected"),
        ("file", 6, "archive copied to removable storage"),
        ("email", 7, "large attachment sent outside the organization"),
        ("logoff", 8, "session ended after correlated data access"),
    )
    for index in range(int(spec["suspicious_count"])):
        activity, hour, detail = scenario[index % len(scenario)]
        sequence += 1
        event_time = start + timedelta(days=6, hours=hour, minutes=index * 3)
        records.append({
            "event_id": f"DEMO-{spec['seed']}-{sequence:05d}",
            "timestamp": event_time.isoformat(),
            "user_id": scenario_user,
            "activity": activity,
            "pc": "DEMO-PC-UNKNOWN" if index == 0 else "DEMO-PC-USB-01",
            "resource": f"DEMO-SYNTHETIC: {detail}",
            "role": role,
            "department": department,
            "label": 1,
        })

    records.sort(key=lambda row: (row["timestamp"], row["event_id"]))
    return records


def validate_demo_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("Demo dataset contains no records.")
    if set(records[0]) != set(EVENT_COLUMNS):
        raise ValueError("Demo dataset does not match the required activity schema.")
    if any(set(record) != set(EVENT_COLUMNS) for record in records):
        raise ValueError("Demo dataset records have inconsistent columns.")
    event_ids = [str(record["event_id"]).strip() for record in records]
    if any(not event_id for event_id in event_ids) or len(event_ids) != len(set(event_ids)):
        raise ValueError("Demo dataset event IDs must be present and unique.")
    parsed_timestamps = [
        datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
        for record in records
    ]
    if parsed_timestamps != sorted(parsed_timestamps):
        raise ValueError("Demo dataset records must be chronologically ordered.")
    if any(not str(record["user_id"]).strip() for record in records):
        raise ValueError("Demo dataset user IDs must be present.")
    if any(int(record["label"]) not in (0, 1) for record in records):
        raise ValueError("Demo dataset labels must be binary.")
    if any(not str(record["role"]).strip() for record in records):
        raise ValueError("Demo dataset role metadata must be present.")

    return {
        "record_count": len(records),
        "unique_users": len({str(record["user_id"]) for record in records}),
        "activity_types": sorted({str(record["activity"]) for record in records}),
        "timestamp_from": parsed_timestamps[0].isoformat(),
        "timestamp_to": parsed_timestamps[-1].isoformat(),
    }


def demo_catalog_with_stats() -> list[dict[str, Any]]:
    catalog = []
    for spec in DEMO_CATALOG:
        records = generate_demo_records(str(spec["key"]))
        summary = validate_demo_records(records)
        catalog.append({
            **spec,
            "demo_id": spec["key"],
            "dataset_type": "Synthetic demonstration",
            "format": "CSV",
            "record_count": summary["record_count"],
            "user_count": summary["unique_users"],
            "activity_types": summary["activity_types"],
            "timestamp_from": summary["timestamp_from"],
            "timestamp_to": summary["timestamp_to"],
            "timestamp_range": {
                "start": summary["timestamp_from"],
                "end": summary["timestamp_to"],
            },
            "source_label": "SYNTHETIC DEMO",
        })
    return catalog


def preview_demo_dataset(dataset_key: str) -> dict[str, Any]:
    records = generate_demo_records(dataset_key)
    summary = validate_demo_records(records)
    activity_counts = Counter(str(row["activity"]) for row in records)
    user_rows: dict[str, dict[str, Any]] = {}
    for row in records:
        profile = user_rows.setdefault(str(row["user_id"]), {
            "user_id": row["user_id"],
            "role": row["role"],
            "department": row["department"],
            "record_count": 0,
            "labelled_suspicious_records": 0,
        })
        profile["record_count"] += 1
        profile["labelled_suspicious_records"] += int(row["label"])

    sample = records[:8]
    suspicious_sample = [row for row in records if row["label"]][:4]
    return {
        "records": records,
        **summary,
        "columns": [
            {"name": column, "type": COLUMN_TYPES[column]}
            for column in EVENT_COLUMNS
        ],
        "sample_records": sample + suspicious_sample,
        "activity_summary": [
            {"activity": activity, "count": count}
            for activity, count in sorted(activity_counts.items())
        ],
        "user_summary": list(user_rows.values()),
        "schema": {
            "source": "Synthetic data generated for UEBA demonstration; not CERT source data.",
            "columns": list(EVENT_COLUMNS),
            "event_id": "Stable, unique synthetic event identifier.",
            "timestamp": "ISO-8601 UTC; records are chronologically ordered.",
            "label": "Synthetic scenario ground truth: 1=scenario event, 0=normal-pattern event.",
        },
    }


def _normal_resource(
    activity: str,
    user_index: int,
    day: int,
    rng: random.Random,
) -> str:
    if activity == "logon":
        return "DEMO-SYNTHETIC: standard workstation sign-in"
    if activity == "file":
        return f"DEMO-SYNTHETIC: /shared/{user_index:02d}/document-{day:02d}.txt"
    if activity == "email":
        return f"DEMO-SYNTHETIC: colleague-{rng.randrange(1, 9):02d}@example.invalid"
    if activity == "web":
        return f"DEMO-SYNTHETIC: https://intranet.example.invalid/page-{day:02d}"
    return "DEMO-SYNTHETIC: approved peripheral check"
