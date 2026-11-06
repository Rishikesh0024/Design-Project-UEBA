from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import datasets
from app.core.config import get_settings
from app.core.security import get_current_user
from app.db.session import Base, get_db
from app.models_db.models import ActivityEvent, AppUser, Dataset, UserProfile
from app.services import ingestion_service
from app.services.demo_datasets import generate_demo_records


@pytest.fixture
def demo_client(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(get_settings(), "DATABASE_URL", "sqlite://")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(ingestion_service, "SessionLocal", test_session)
    with test_session() as db:
        db.add(AppUser(
            id=1,
            email="analyst@demo.test",
            full_name="Demo Analyst",
            hashed_pw="unused",
            role="analyst",
        ))
        db.commit()

    app = FastAPI()
    app.include_router(datasets.router, prefix="/api/v1")
    app.include_router(datasets.demo_router, prefix="/api")

    def override_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AppUser(
        id=1,
        email="analyst@demo.test",
        full_name="Demo Analyst",
        hashed_pw="unused",
        role="analyst",
    )
    with TestClient(app) as client:
        yield client, test_session
    engine.dispose()


def test_demo_load_fails_closed_when_postgres_falls_back_to_sqlite(demo_client, monkeypatch):
    client, session_factory = demo_client
    monkeypatch.setattr(get_settings(), "DATABASE_URL", "postgresql://db.invalid/ueba_test")

    response = client.post("/api/datasets/demo/cert-activity/load")

    assert response.status_code == 503
    assert "Configured PostgreSQL is unavailable" in response.json()["detail"]
    with session_factory() as db:
        assert db.query(Dataset).filter_by(is_demo=True).count() == 0


def test_demo_preview_is_reproducible_and_describes_synthetic_schema(demo_client):
    client, _ = demo_client

    catalog = client.get("/api/datasets/demo")
    assert catalog.status_code == 200
    assert len(catalog.json()) == 3
    assert client.get("/api/v1/datasets/demo/catalog").json() == catalog.json()
    for demo in catalog.json():
        assert demo["demo_id"] == demo["key"]
        assert demo["dataset_type"] == "Synthetic demonstration"
        assert demo["timestamp_range"]["start"] == demo["timestamp_from"]
        assert demo["timestamp_range"]["end"] == demo["timestamp_to"]
        preview = client.get(f"/api/datasets/demo/{demo['demo_id']}/preview")
        assert preview.status_code == 200
        assert preview.json()["record_count"] == demo["record_count"]
        assert preview.json()["dataset_type"] == "Synthetic demonstration"
        assert preview.json()["timestamp_range"]["start"] == demo["timestamp_from"]

    first = client.get("/api/v1/datasets/demo/ueba-threat-scenario/preview")
    second = client.get("/api/v1/datasets/demo/ueba-threat-scenario/preview")

    assert first.status_code == second.status_code == 200
    preview = first.json()
    assert preview["source_label"] == "SYNTHETIC DEMO"
    assert preview["record_count"] == len(generate_demo_records("ueba-threat-scenario"))
    assert preview["timestamp_from"].startswith("2025-02-03")
    assert preview["timestamp_to"].startswith("2025-02-09")
    assert preview["user_count"] == 8
    assert set(preview["activity_types"]) == {"logon", "logoff", "file", "email", "web", "device"}
    assert {column["name"] for column in preview["columns"]} >= {
        "event_id", "timestamp", "user_id", "activity", "pc", "resource", "role", "label"
    }
    assert preview["sample_records"] == second.json()["sample_records"]
    assert any(record["label"] == 1 for record in preview["sample_records"])


@pytest.mark.parametrize(
    "demo_id",
    ["cert-activity", "user-behaviour", "ueba-threat-scenario"],
)
def test_load_demo_uses_ingestion_and_preserves_labels_roles_and_ids(demo_client, demo_id):
    client, session_factory = demo_client
    catalog = client.get("/api/datasets/demo").json()
    expected_records = next(item["record_count"] for item in catalog if item["demo_id"] == demo_id)
    response = client.post(f"/api/datasets/demo/{demo_id}/load")

    assert response.status_code == 201
    created = response.json()
    assert created["is_demo"] is True
    assert "SYNTHETIC DEMO" in created["name"]
    with session_factory() as db:
        dataset = db.get(Dataset, created["id"])
        events = db.query(ActivityEvent).filter_by(dataset_id=created["id"]).order_by(
            ActivityEvent.timestamp, ActivityEvent.event_id
        ).all()
        profiles = db.query(UserProfile).filter_by(dataset_id=created["id"]).all()
        assert dataset.status == "ready"
        assert dataset.valid_rows == expected_records
        assert len(events) == dataset.valid_rows
        assert len({event.event_id for event in events}) == len(events)
        assert [event.timestamp for event in events] == sorted(event.timestamp for event in events)
        assert {event.activity for event in events} >= {"logon", "logoff", "file", "email", "web", "device"}
        assert {event.label for event in events} == {0, 1}
        assert len(profiles) == 8
        assert all(profile.role and profile.department for profile in profiles)
        assert dataset.has_labels is True
        assert dataset.schema_info["source"].startswith("Synthetic demonstration data")
        duplicate = client.post(f"/api/datasets/demo/{demo_id}/load")
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == created["id"]
        with session_factory() as db:
            assert db.query(Dataset).filter_by(is_demo=True, version=created["version"]).count() == 1


def test_reset_demo_rebuilds_only_demo_events_and_remove_demo_is_safe(demo_client):
    client, session_factory = demo_client
    real_dataset = Dataset(
        name="Uploaded data",
        version="r4.2",
        file_path="/outside/demo",
        status="ready",
        uploaded_by=1,
        is_demo=False,
    )
    with session_factory() as db:
        db.add(real_dataset)
        db.flush()
        real_dataset_id = real_dataset.id
        db.add(ActivityEvent(
            dataset_id=real_dataset.id,
            event_id="real-event",
            user_id="real-user",
            activity="logon",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ))
        db.commit()

    loaded = client.post("/api/v1/datasets/demo/cert-activity/load").json()
    demo_id = loaded["id"]
    reset = client.post(f"/api/v1/datasets/{demo_id}/reset-demo")
    assert reset.status_code == 200
    assert reset.json()["is_demo"] is True

    with session_factory() as db:
        assert db.query(ActivityEvent).filter_by(dataset_id=real_dataset_id).count() == 1
        assert db.query(Dataset).filter_by(id=real_dataset_id).one().is_demo is False
        assert db.query(ActivityEvent).filter_by(dataset_id=demo_id).count() == len(
            generate_demo_records("cert-activity")
        )

    not_demo = client.post(f"/api/v1/datasets/{real_dataset_id}/reset-demo")
    assert not_demo.status_code == 400
    removed = client.delete(f"/api/v1/datasets/{demo_id}")
    assert removed.status_code == 204
    with session_factory() as db:
        assert db.get(Dataset, demo_id) is None
        assert db.query(ActivityEvent).filter_by(dataset_id=real_dataset_id).count() == 1


def test_demo_seed_version_is_unique_but_uploaded_versions_are_not(demo_client):
    _, session_factory = demo_client
    with session_factory() as db:
        db.add_all([
            Dataset(name="Demo 1", version="demo-v1", file_path="/tmp/demo-1", is_demo=True),
            Dataset(name="Demo 2", version="demo-v1", file_path="/tmp/demo-2", is_demo=True),
        ])
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add_all([
            Dataset(name="Upload 1", version="r4.2", file_path="/tmp/upload-1", is_demo=False),
            Dataset(name="Upload 2", version="r4.2", file_path="/tmp/upload-2", is_demo=False),
        ])
        db.commit()
