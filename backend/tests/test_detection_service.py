from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password, verify_password
from app.db.session import Base
from app.models_db.models import ActivityEvent, Dataset, UserProfile
from app.services.detection_service import _branch_scores, _evaluate
from app.services import ingestion_service
from app.services.ingestion_service import _column_map, _normalize_activity


def _events(labels: bool = True) -> pd.DataFrame:
    rows = []
    for day in pd.date_range("2026-01-01", periods=12, tz="UTC"):
        for user, role in (("u001", "analyst"), ("u002", "engineer")):
            activities = ["logon", "file", "email"]
            if user == "u001" and day.day >= 10:
                activities.append("device")
            for index, activity in enumerate(activities):
                rows.append({
                    "event_id": f"{user}-{day.day}-{index}",
                    "timestamp": day + pd.Timedelta(hours=9 + index),
                    "user": user,
                    "activity": activity,
                    "pc": "pc-1",
                    "resource": f"{user}-{activity}-{index if day.day >= 10 else 0}",
                    "label": int(labels and user == "u001" and day.day >= 10),
                    "role": role,
                    "date": day.date(),
                })
    return pd.DataFrame(rows)


def test_three_empirical_branches_are_bounded_and_chronological():
    daily, metadata = _branch_scores(_events(), 0.7)

    assert {"temporal_score", "relational_score", "contextual_score"} <= set(daily.columns)
    assert daily["in_train"].any()
    assert (~daily["in_train"]).any()
    for column in ("temporal_score", "relational_score", "contextual_score"):
        assert daily[column].between(0, 1).all()
    assert metadata["train_end"] < str(max(daily["date"]))


def test_evaluation_metrics_only_exist_for_labeled_heldout_data():
    daily, _ = _branch_scores(_events(), 0.7)
    daily["risk_score"] = (
        daily["temporal_score"] * 40
        + daily["relational_score"] * 30
        + daily["contextual_score"] * 30
    )
    daily["is_anomaly"] = ~daily["in_train"] & daily["risk_score"].ge(40)

    metrics = _evaluate(daily)
    assert metrics is not None
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["pr_auc"] <= 1
    assert 0 <= metrics["roc_auc"] <= 1
    assert len(metrics["roc_curve"]) == 2
    assert len(metrics["precision_recall_curve"]) == 2
    assert len(metrics["roc_curve"][0]) == len(metrics["roc_curve"][1])
    assert len(metrics["precision_recall_curve"][0]) == len(
        metrics["precision_recall_curve"][1]
    )
    assert metrics["top_k"] >= 1
    assert len(metrics["confusion_matrix"]) == 2

    unlabeled, _ = _branch_scores(_events(labels=False), 0.7)
    unlabeled["risk_score"] = 20.0
    unlabeled["is_anomaly"] = False
    assert _evaluate(unlabeled) is None


def test_cert_type_and_column_alias_normalization():
    assert _normalize_activity("GET", Path("000_HTTP.csv")) == "web"
    assert _normalize_activity("Connect", Path("005_device.csv")) == "device"
    assert _column_map(["ID", "Date", "User", "PC", "Filename", "Activity"]) == {
        "event_id": "ID",
        "timestamp": "Date",
        "user": "User",
        "activity": "Activity",
        "pc": "PC",
        "resource": "Filename",
    }


def test_ingestion_excludes_role_metadata_from_activity_record_counts(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(ingestion_service, "SessionLocal", test_session)

    dataset_path = tmp_path / "cert"
    dataset_path.mkdir()
    (dataset_path / "logon.csv").write_text(
        "id,date,user,activity\nE001,2026-01-01T10:00:00Z,u001,Logon\n",
        encoding="utf-8",
    )
    (dataset_path / "users.csv").write_text(
        "user,role,department\nu001,analyst,security\n",
        encoding="utf-8",
    )

    with test_session() as db:
        dataset = Dataset(name="CERT test", file_path=str(dataset_path))
        db.add(dataset)
        db.commit()
        dataset_id = dataset.id

    ingestion_service.ingest_dataset(dataset_id)

    with test_session() as db:
        dataset = db.get(Dataset, dataset_id)
        assert dataset is not None
        assert dataset.total_rows == 1
        assert dataset.valid_rows == 1
        assert dataset.quality_report["record_count"] == 1
        assert dataset.quality_report["missing_or_invalid_records"] == 0
        assert dataset.schema_info["role_metadata_rows"] == 1
        assert db.scalar(select(ActivityEvent).where(
            ActivityEvent.dataset_id == dataset_id
        )) is not None
        profile = db.scalar(select(UserProfile).where(
            UserProfile.dataset_id == dataset_id,
            UserProfile.user_id == "u001",
        ))
        assert profile is not None
        assert profile.role == "analyst"
        assert profile.department == "security"


def test_password_hashing_and_legacy_bcrypt_verification():
    hashed = hash_password("strong-password-example")
    assert hashed.startswith("$argon2")
    assert verify_password("strong-password-example", hashed)
    assert not verify_password("incorrect-password", hashed)
