from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models_db.models import ActivityEvent, AppUser, Dataset, ModelRun, RiskScore

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


def _run_output(run: ModelRun) -> dict:
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "branch": run.branch,
        "status": run.status,
        "version": run.version,
        "train_config": run.train_config,
        "eval_metrics": run.eval_metrics,
        "train_rows": run.train_rows,
        "eval_rows": run.eval_rows,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
    }


@router.get("/{dataset_id}")
def list_completed_experiments(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    candidates = (
        db.query(ModelRun)
        .filter(
            ModelRun.dataset_id == dataset_id,
            ModelRun.status == "ready",
        )
        .order_by(ModelRun.finished_at.desc())
        .all()
    )
    return [
        _run_output(run)
        for run in candidates
        if isinstance(run.eval_metrics, dict) and run.eval_metrics
    ]


@router.get("/{dataset_id}/runs")
def list_completed_runs(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    runs = (
        db.query(ModelRun)
        .filter(
            ModelRun.dataset_id == dataset_id,
            ModelRun.status == "ready",
        )
        .order_by(ModelRun.finished_at.desc())
        .all()
    )
    return [_run_output(run) for run in runs]


@router.get("/{dataset_id}/graph/snapshots")
def list_graph_snapshots(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    snapshot_date = func.date(ActivityEvent.timestamp)
    dates = (
        db.query(snapshot_date)
        .filter(ActivityEvent.dataset_id == dataset_id)
        .distinct()
        .order_by(snapshot_date.desc())
        .limit(1000)
        .all()
    )
    return {"items": [str(row[0]) for row in dates if row[0] is not None]}


@router.get("/{dataset_id}/graph")
def get_observed_relationship_graph(
    dataset_id: int,
    snapshot_date: date | None = Query(None),
    user_search: str | None = Query(None, max_length=100),
    edge_limit: int = Query(150, ge=1, le=300),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    query = db.query(ActivityEvent).filter(ActivityEvent.dataset_id == dataset_id)
    if snapshot_date:
        query = query.filter(func.date(ActivityEvent.timestamp) == snapshot_date)
    if user_search:
        query = query.filter(ActivityEvent.user_id.ilike(f"%{user_search}%"))

    users = query.with_entities(func.count(func.distinct(ActivityEvent.user_id))).scalar() or 0
    resources = query.with_entities(
        func.count(func.distinct(ActivityEvent.resource))
    ).filter(ActivityEvent.resource.is_not(None), ActivityEvent.resource != "").scalar() or 0
    devices = query.with_entities(
        func.count(func.distinct(ActivityEvent.pc))
    ).filter(ActivityEvent.pc.is_not(None), ActivityEvent.pc != "").scalar() or 0
    resource_edges = (
        query.with_entities(
            ActivityEvent.user_id,
            ActivityEvent.resource,
            func.count(ActivityEvent.id).label("event_count"),
        )
        .filter(ActivityEvent.resource.is_not(None), ActivityEvent.resource != "")
        .group_by(ActivityEvent.user_id, ActivityEvent.resource)
        .order_by(func.count(ActivityEvent.id).desc())
        .limit(edge_limit)
        .all()
    )
    resource_relationships = (
        query.with_entities(ActivityEvent.user_id, ActivityEvent.resource)
        .filter(ActivityEvent.resource.is_not(None), ActivityEvent.resource != "")
        .group_by(ActivityEvent.user_id, ActivityEvent.resource)
        .count()
    )
    device_edges = (
        query.with_entities(
            ActivityEvent.user_id,
            ActivityEvent.pc,
            func.count(ActivityEvent.id).label("event_count"),
        )
        .filter(ActivityEvent.pc.is_not(None), ActivityEvent.pc != "")
        .group_by(ActivityEvent.user_id, ActivityEvent.pc)
        .order_by(func.count(ActivityEvent.id).desc())
        .limit(edge_limit)
        .all()
    )
    device_relationships = (
        query.with_entities(ActivityEvent.user_id, ActivityEvent.pc)
        .filter(ActivityEvent.pc.is_not(None), ActivityEvent.pc != "")
        .group_by(ActivityEvent.user_id, ActivityEvent.pc)
        .count()
    )

    nodes: dict[str, dict] = {}
    edges = []
    for user_id, resource, count in resource_edges:
        source = f"user:{user_id}"
        target = f"resource:{resource}"
        nodes.setdefault(source, {"id": source, "type": "user", "label": user_id})
        nodes.setdefault(target, {"id": target, "type": "resource", "label": resource})
        edges.append({
            "id": f"{source}->{target}",
            "source": source,
            "target": target,
            "type": "user-resource",
            "label": "resource interaction",
            "event_count": count,
        })
    for user_id, pc, count in device_edges:
        source = f"user:{user_id}"
        target = f"device:{pc}"
        nodes.setdefault(source, {"id": source, "type": "user", "label": user_id})
        nodes.setdefault(target, {"id": target, "type": "device", "label": pc})
        edges.append({
            "id": f"{source}->{target}",
            "source": source,
            "target": target,
            "type": "user-device",
            "label": "device interaction",
            "event_count": count,
        })
    possible_relationships = users * (resources + devices)
    relationship_count = resource_relationships + device_relationships
    return {
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "snapshot_count": (
            db.query(func.count(func.distinct(func.date(ActivityEvent.timestamp))))
            .filter(ActivityEvent.dataset_id == dataset_id)
            .scalar()
            or 0
        ),
        "node_counts": {"user": users, "resource": resources, "device": devices},
        "relationship_count": relationship_count,
        "graph_density": (
            relationship_count / possible_relationships
            if possible_relationships
            else None
        ),
        "displayed_relationship_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
        "truncated": len(resource_edges) == edge_limit or len(device_edges) == edge_limit,
        "source": "observed activity event relationships; no HGT model inference",
    }


@router.get("/{dataset_id}/score-fusion")
def get_score_fusion_data(
    dataset_id: int,
    model_run_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    runs_query = db.query(ModelRun).filter(
        ModelRun.dataset_id == dataset_id,
        ModelRun.status == "ready",
    )
    run = (
        db.get(ModelRun, model_run_id)
        if model_run_id is not None
        else runs_query.order_by(ModelRun.finished_at.desc()).first()
    )
    if run is None or run.dataset_id != dataset_id or run.status != "ready":
        return {"model_run_id": None, "weights": None, "scores": [], "total": 0}
    score_query = db.query(RiskScore).filter(
        RiskScore.dataset_id == dataset_id,
        RiskScore.model_run_id == run.id,
        RiskScore.in_train.is_(False),
    )
    total = score_query.count()
    rows = (
        score_query.order_by(RiskScore.window_date, RiskScore.user_id)
        .limit(5000)
        .all()
    )
    return {
        "model_run_id": run.id,
        "weights": (run.train_config or {}).get("fusion_weights"),
        "total": total,
        "scores": [
            {
                "user_id": row.user_id,
                "window_date": row.window_date,
                "temporal_score": row.temporal_score,
                "relational_score": row.relational_score,
                "contextual_score": row.contextual_score,
                "risk_score": row.risk_score,
                "risk_weights": row.fusion_weights,
            }
            for row in rows
        ],
        "truncated": total > len(rows),
    }
