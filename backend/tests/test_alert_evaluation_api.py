from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import alerts, evaluation
from app.core.security import get_current_user
from app.db.session import Base, get_db
from app.models_db.models import (
    ActivityEvent,
    Alert,
    AlertEvidence,
    AppUser,
    Dataset,
    ModelRun,
    RiskScore,
    UserProfile,
)


@pytest.fixture
def api_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with test_session() as db:
        analyst = AppUser(
            id=1,
            email="analyst@test.local",
            full_name="Test Analyst",
            hashed_pw="unused",
            role="analyst",
        )
        dataset = Dataset(name="API fixture", version="r4.2", file_path="/tmp/fixture")
        db.add_all([analyst, dataset])
        db.flush()
        run = ModelRun(
            dataset_id=dataset.id,
            branch="fusion",
            status="ready",
            version="empirical-test",
            train_config={"fusion_weights": {
                "w_temporal": 0.4,
                "w_relational": 0.3,
                "w_contextual": 0.3,
            }},
            eval_metrics={"precision": 0.8, "confusion_matrix": [[3, 1], [1, 2]]},
            train_rows=10,
            eval_rows=5,
            finished_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        db.add(run)
        db.flush()
        db.add(ModelRun(
            dataset_id=dataset.id,
            branch="fusion",
            status="ready",
            version="unlabeled-test",
            eval_metrics=None,
            train_rows=10,
            eval_rows=5,
            finished_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        ))
        for alert_uid, user_id, risk, severity in (
            ("alert-critical", "user-1", 91.0, "critical"),
            ("alert-high", "user-1", 71.0, "high"),
            ("alert-medium", "user-2", 42.0, "medium"),
        ):
            alert = Alert(
                alert_uid=alert_uid,
                dataset_id=dataset.id,
                model_run_id=run.id,
                user_id=user_id,
                window_date="2026-01-02",
                primary_activity="file",
                risk_score=risk,
                temporal_score=0.8,
                relational_score=0.7,
                contextual_score=0.6,
                threshold_value=60,
                severity=severity,
                status="open",
                explanation="Persisted fixture explanation",
                created_at=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
                evidence=[AlertEvidence(
                    event_id=f"{alert_uid}-event",
                    activity="file",
                    timestamp=datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
                    resource="shared-resource",
                )],
            )
            db.add(alert)
        db.add(UserProfile(
            dataset_id=dataset.id,
            user_id="user-1",
            role="analyst",
            department="security",
            total_events=12,
            baseline={"baseline_source": "user"},
        ))
        db.add_all([
            ActivityEvent(
                dataset_id=dataset.id,
                event_id="event-1",
                user_id="user-1",
                activity="file",
                timestamp=datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
                pc="device-1",
                resource="resource-1",
            ),
            ActivityEvent(
                dataset_id=dataset.id,
                event_id="event-2",
                user_id="user-2",
                activity="email",
                timestamp=datetime(2026, 1, 2, 11, tzinfo=timezone.utc),
                pc="device-2",
                resource="resource-2",
            ),
            RiskScore(
                model_run_id=run.id,
                dataset_id=dataset.id,
                user_id="user-1",
                window_date="2026-01-02",
                temporal_score=0.8,
                relational_score=0.7,
                contextual_score=0.6,
                risk_score=71,
                in_train=False,
                fusion_weights=run.train_config["fusion_weights"],
            ),
        ])
        db.commit()
        dataset_id = dataset.id
        run_id = run.id

    app = FastAPI()
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(evaluation.router, prefix="/api/v1")

    def override_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AppUser(
        id=1,
        email="analyst@test.local",
        full_name="Test Analyst",
        hashed_pw="unused",
        role="analyst",
    )
    with TestClient(app) as client:
        yield client, dataset_id, run_id
    engine.dispose()


def test_alert_summary_uses_persisted_severity_and_risk_scores(api_client):
    client, dataset_id, _ = api_client

    response = client.get(f"/api/v1/alerts/summary?dataset_id={dataset_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["total_alerts"] == 3
    assert data["average_risk_score"] == 68
    assert data["severity_counts"] == {
        "critical": 1,
        "high": 1,
        "medium": 1,
        "low": 0,
    }
    assert sum(row["count"] for row in data["score_distribution"]) == 3


def test_alert_pagination_search_and_risk_order(api_client):
    client, dataset_id, _ = api_client

    response = client.get(
        f"/api/v1/alerts/paged?dataset_id={dataset_id}&user_id=user-1&limit=1&offset=0"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["items"][0]["alert_uid"] == "alert-critical"
    next_page = client.get(
        f"/api/v1/alerts/paged?dataset_id={dataset_id}&user_id=user-1&limit=1&offset=1"
    ).json()
    assert next_page["items"][0]["alert_uid"] == "alert-high"

    by_id = client.get(
        f"/api/v1/alerts/paged?dataset_id={dataset_id}&alert_id=medium"
    ).json()
    assert [row["alert_uid"] for row in by_id["items"]] == ["alert-medium"]

    filtered = client.get(
        f"/api/v1/alerts/paged?dataset_id={dataset_id}&severity=high&status=open"
        "&date_from=2026-01-02T00:00:00Z&date_to=2026-01-02T23:59:59Z"
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["alert_uid"] == "alert-high"


def test_alert_investigation_includes_entity_branch_evidence_and_reviews(api_client):
    client, dataset_id, _ = api_client
    alert = client.get(f"/api/v1/alerts?dataset_id={dataset_id}&limit=1").json()[0]

    response = client.get(f"/api/v1/alerts/{alert['id']}/investigation")

    assert response.status_code == 200
    data = response.json()
    assert data["entity"]["role"] == "analyst"
    assert data["entity"]["department"] == "security"
    assert data["alert"]["temporal_score"] == 0.8
    assert data["alert"]["evidence"][0]["event_id"] == "alert-critical-event"
    assert data["fusion_weights"]["w_relational"] == 0.3
    assert data["reviews"] == []


def test_evaluation_graph_is_built_from_observed_event_relationships(api_client):
    client, dataset_id, _ = api_client
    snapshots = client.get(f"/api/v1/evaluation/{dataset_id}/graph/snapshots")
    assert snapshots.status_code == 200
    assert snapshots.json()["items"] == ["2026-01-02"]

    response = client.get(
        f"/api/v1/evaluation/{dataset_id}/graph?snapshot_date=2026-01-02&user_search=user-1"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["node_counts"] == {"user": 1, "resource": 1, "device": 1}
    assert data["relationship_count"] == 2
    assert {edge["type"] for edge in data["edges"]} == {"user-resource", "user-device"}
    assert all(edge["event_count"] == 1 for edge in data["edges"])
    assert "no HGT model inference" in data["source"]


def test_evaluation_runs_and_fusion_scores_are_persisted_only(api_client):
    client, dataset_id, run_id = api_client
    runs = client.get(f"/api/v1/evaluation/{dataset_id}")
    assert runs.status_code == 200
    assert runs.json()[0]["id"] == run_id
    assert len(runs.json()) == 1
    all_runs = client.get(f"/api/v1/evaluation/{dataset_id}/runs")
    assert all_runs.status_code == 200
    assert len(all_runs.json()) == 2
    assert any(run["eval_metrics"] is None for run in all_runs.json())

    response = client.get(
        f"/api/v1/evaluation/{dataset_id}/score-fusion?model_run_id={run_id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model_run_id"] == run_id
    assert data["weights"]["w_temporal"] == 0.4
    assert data["scores"][0]["user_id"] == "user-1"
    assert data["scores"][0]["relational_score"] == 0.7
