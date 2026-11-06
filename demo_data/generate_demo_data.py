"""
generate_demo_data.py
---------------------
Generates a reproducible synthetic UEBA activity log.

Design decisions
----------------
* 30 users across 4 roles over 60 days.
* Normal behaviour follows role-specific working-hour patterns.
* Three users have planted anomalies in the final 10 days:
    - u003 : after-hours logon spike + high file volume  (insider exfil pattern)
    - u011 : removable-device usage spike                (data theft pattern)
    - u022 : unusual web activity + new resources        (recon pattern)
* A 'label' column marks rows that belong to the planted anomaly windows
  so evaluation metrics can be computed.
* This is SYNTHETIC data. It does not represent real employees.
"""

import random
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
random.seed(SEED)

OUT_DIR = Path(__file__).parent
EVENTS_FILE = OUT_DIR / "demo_events.csv"
USERS_FILE  = OUT_DIR / "demo_users.csv"

# ── Configuration ────────────────────────────────────────────────────────────
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
DAYS       = 60
N_USERS    = 30

ROLES = {
    "engineer":   {"count": 10, "work_hours": (8, 18),  "file_rate": 8,  "web_rate": 4,  "email_rate": 5},
    "analyst":    {"count":  8, "work_hours": (9, 17),  "file_rate": 5,  "web_rate": 6,  "email_rate": 8},
    "manager":    {"count":  6, "work_hours": (8, 19),  "file_rate": 3,  "web_rate": 5,  "email_rate": 10},
    "hr":         {"count":  6, "work_hours": (9, 17),  "file_rate": 2,  "web_rate": 3,  "email_rate": 12},
}

ANOMALY_USERS = {
    "u003": "exfil",
    "u011": "device",
    "u022": "recon",
}
ANOMALY_START_DAY = 50   # anomalies begin on day 50 of 60


def rand_ts(base_date: datetime, hour_min: int, hour_max: int) -> datetime:
    h = random.randint(hour_min, hour_max - 1)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return base_date.replace(hour=h, minute=m, second=s)


def fmt(dt: datetime) -> str:
    return dt.strftime("%m/%d/%Y %H:%M:%S")


def build_users() -> list[dict]:
    users = []
    uid = 1
    for role, cfg in ROLES.items():
        for _ in range(cfg["count"]):
            users.append({
                "user_id": f"u{uid:03d}",
                "role":    role,
                "dept":    role.capitalize(),
                "pc":      f"PC-{uid:03d}",
            })
            uid += 1
    return users


def generate_events(users: list[dict]) -> list[dict]:
    rows = []
    eid  = 1

    for day_offset in range(DAYS):
        date = START_DATE + timedelta(days=day_offset)
        is_weekend = date.weekday() >= 5
        is_anomaly_window = day_offset >= ANOMALY_START_DAY

        for user in users:
            uid  = user["user_id"]
            role = user["role"]
            cfg  = ROLES[role]
            wh   = cfg["work_hours"]
            pc   = user["pc"]

            # Skip weekends for most users (80 % chance)
            if is_weekend and random.random() < 0.80:
                continue

            anomaly_type = ANOMALY_USERS.get(uid) if is_anomaly_window else None

            # ── Logon ────────────────────────────────────────────────────────
            n_logons = random.randint(1, 3)
            if anomaly_type == "exfil":
                n_logons += random.randint(3, 6)

            for _ in range(n_logons):
                if anomaly_type == "exfil" and random.random() < 0.6:
                    ts = rand_ts(date, 20, 23)   # after hours
                    label = 1
                else:
                    ts = rand_ts(date, wh[0], wh[1])
                    label = 0
                rows.append({
                    "id": f"E{eid:07d}", "date": fmt(ts),
                    "user": uid, "pc": pc,
                    "activity": "Logon", "label": label,
                })
                eid += 1

            # ── File access ──────────────────────────────────────────────────
            n_files = random.randint(0, cfg["file_rate"])
            if anomaly_type == "exfil":
                n_files += random.randint(20, 40)

            for i in range(n_files):
                ts = rand_ts(date, wh[0], wh[1])
                if anomaly_type == "exfil" and i >= cfg["file_rate"]:
                    ts = rand_ts(date, 20, 23)
                    label = 1
                    resource = f"/sensitive/project_alpha/doc_{random.randint(1,5)}.docx"
                else:
                    label = 0
                    resource = f"/shared/docs/file_{random.randint(1, 30)}.txt"
                rows.append({
                    "id": f"E{eid:07d}", "date": fmt(ts),
                    "user": uid, "pc": pc,
                    "activity": "File", "label": label,
                    "resource": resource,
                })
                eid += 1

            # ── Email ────────────────────────────────────────────────────────
            n_emails = random.randint(0, cfg["email_rate"])
            for _ in range(n_emails):
                ts = rand_ts(date, wh[0], wh[1])
                rows.append({
                    "id": f"E{eid:07d}", "date": fmt(ts),
                    "user": uid, "pc": pc,
                    "activity": "Email", "label": 0,
                    "resource": f"colleague{random.randint(1,20)}@company.com",
                })
                eid += 1

            # ── Web ──────────────────────────────────────────────────────────
            n_web = random.randint(0, cfg["web_rate"])
            if anomaly_type == "recon":
                n_web += random.randint(15, 30)

            for i in range(n_web):
                ts = rand_ts(date, wh[0], wh[1])
                if anomaly_type == "recon" and i >= cfg["web_rate"]:
                    label = 1
                    resource = f"http://external-site-{random.randint(100,199)}.com"
                else:
                    label = 0
                    resource = f"http://intranet/page{random.randint(1,20)}"
                rows.append({
                    "id": f"E{eid:07d}", "date": fmt(ts),
                    "user": uid, "pc": pc,
                    "activity": "WWW", "label": label,
                    "resource": resource,
                })
                eid += 1

            # ── Removable device ─────────────────────────────────────────────
            if anomaly_type == "device":
                n_dev = random.randint(3, 8)
                for _ in range(n_dev):
                    ts = rand_ts(date, wh[0], wh[1])
                    rows.append({
                        "id": f"E{eid:07d}", "date": fmt(ts),
                        "user": uid, "pc": pc,
                        "activity": "Device", "label": 1,
                        "resource": f"USB_{random.randint(1,5)}",
                    })
                    eid += 1
            elif random.random() < 0.02:   # rare normal device use
                ts = rand_ts(date, wh[0], wh[1])
                rows.append({
                    "id": f"E{eid:07d}", "date": fmt(ts),
                    "user": uid, "pc": pc,
                    "activity": "Device", "label": 0,
                    "resource": "USB_backup",
                })
                eid += 1

    return rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows):,} rows → {path}")


if __name__ == "__main__":
    print("Generating synthetic UEBA demo dataset …")
    users  = build_users()
    events = generate_events(users)

    write_csv(
        EVENTS_FILE, events,
        ["id", "date", "user", "pc", "activity", "resource", "label"],
    )
    write_csv(
        USERS_FILE, users,
        ["user_id", "role", "dept", "pc"],
    )
    print(f"  Anomaly users : {list(ANOMALY_USERS.keys())} (days {ANOMALY_START_DAY}–{DAYS})")
    print("Done.")
