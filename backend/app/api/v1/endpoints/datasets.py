"""Dataset upload, validation, listing, and status endpoints."""
from __future__ import annotations
import csv
import logging
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models_db.models import (
    ActivityEvent,
    Alert,
    AlertEvidence,
    AnalystReview,
    AppUser,
    BaselineUpdate,
    BranchScore,
    Dataset,
    DriftEvent,
    ModelRun,
    ProcessingJob,
    RiskScore,
    ThresholdVersion,
    UserProfile,
)
from app.schemas.schemas import DatasetOut, DatasetDetail, JobOut
from app.services.demo_datasets import (
    DEMO_CATALOG,
    demo_catalog_with_stats,
    generate_demo_records,
    preview_demo_dataset,
    validate_demo_records,
)
from app.services.ingestion_service import ingest_dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])
demo_router = APIRouter(prefix="/datasets", tags=["datasets"])
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(get_settings().UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 2 * 1024 ** 3
DEMO_BY_KEY = {str(item["key"]): item for item in DEMO_CATALOG}


@router.post("", response_model=DatasetOut, status_code=201)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    version: str = Form("r4.2"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    if not name.strip():
        raise HTTPException(422, "Dataset name cannot be empty.")
    if not files or any(
        not file.filename or Path(file.filename).suffix.lower() != ".csv"
        for file in files
    ):
        raise HTTPException(400, "Upload one or more CSV files.")

    upload_dir = UPLOAD_DIR / str(uuid4())
    upload_dir.mkdir(parents=True, exist_ok=False)
    bytes_written = 0
    try:
        for index, file in enumerate(files):
            filename = Path(file.filename or f"upload-{index}.csv").name
            dest = upload_dir / f"{index:03d}_{filename}"
            with dest.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "Combined upload exceeds 2 GB.")
                    target.write(chunk)
            await file.close()
    except Exception:
        for stored_file in upload_dir.iterdir():
            stored_file.unlink()
        upload_dir.rmdir()
        raise

    dataset = Dataset(
        name=name.strip(), version=version,
        file_path=str(upload_dir),
        uploaded_by=current_user.id if (current_user and current_user.id > 0) else None,
    )
    try:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    except Exception:
        db.rollback()
        for stored_file in upload_dir.iterdir():
            stored_file.unlink()
        upload_dir.rmdir()
        raise

    background_tasks.add_task(ingest_dataset, dataset.id)
    return dataset


@demo_router.get("/demo/catalog")
@router.get("/demo/catalog")
def list_demo_datasets(
    _: AppUser = Depends(get_current_user),
):
    return demo_catalog_with_stats()


@demo_router.get("/demo")
@router.get("/demo")
def list_demo_datasets_alias(
    _: AppUser = Depends(get_current_user),
):
    return demo_catalog_with_stats()


@demo_router.get("/demo/{dataset_key}/preview")
@router.get("/demo/{dataset_key}/preview")
def get_demo_preview(
    dataset_key: str,
    _: AppUser = Depends(get_current_user),
):
    if dataset_key not in DEMO_BY_KEY:
        raise HTTPException(404, "Demo dataset not found.")
    preview = preview_demo_dataset(dataset_key)
    spec = DEMO_BY_KEY[dataset_key]
    return {
        "key": dataset_key,
        "demo_id": dataset_key,
        "name": spec["name"],
        "dataset_type": "Synthetic demonstration",
        "source_label": "SYNTHETIC DEMO",
        "format": "CSV",
        "record_count": len(preview["records"]),
        "user_count": len(preview["user_summary"]),
        "activity_types": sorted({row["activity"] for row in preview["records"]}),
        "timestamp_range": {
            "start": preview["timestamp_from"],
            "end": preview["timestamp_to"],
        },
        **{key: value for key, value in preview.items() if key != "records"},
    }


@demo_router.post("/demo/{dataset_key}/load", response_model=DatasetOut, status_code=201)
@router.post("/demo/{dataset_key}/load", response_model=DatasetOut, status_code=201)
def load_demo_dataset(
    dataset_key: str,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    spec = DEMO_BY_KEY.get(dataset_key)
    if spec is None:
        raise HTTPException(404, "Demo dataset not found.")
    if (
        get_settings().DATABASE_URL.lower().startswith("postgresql")
        and db.get_bind().dialect.name != "postgresql"
    ):
        logger.error(
            "Refusing demo import: PostgreSQL is configured but the active database is %s.",
            db.get_bind().dialect.name,
        )
        raise HTTPException(
            status_code=503,
            detail="Configured PostgreSQL is unavailable; the demo dataset was not imported.",
        )

    version = f"demo-synthetic-v1-seed-{spec['seed']}"
    existing = db.scalar(select(Dataset).where(
        Dataset.is_demo.is_(True),
        Dataset.version == version,
    ))
    if existing is not None:
        if existing.status in {"uploaded", "validating", "processing"}:
            raise HTTPException(409, "This demo dataset is already being processed.")
        if existing.status == "ready":
            response.status_code = 200
            return existing
        _delete_dataset_records(db, existing.id)
        existing.status = "uploaded"
        existing.total_rows = 0
        existing.valid_rows = 0
        existing.unique_users = 0
        existing.date_from = None
        existing.date_to = None
        existing.has_labels = False
        existing.quality_report = None
        db.commit()
        db.refresh(existing)
        upload_dir = Path(existing.file_path)
        upload_dir.mkdir(parents=True, exist_ok=True)
    else:
        upload_dir = UPLOAD_DIR / f"demo-{dataset_key}-{uuid4()}"
        upload_dir.mkdir(parents=True, exist_ok=False)
    try:
        records = generate_demo_records(dataset_key)
        summary = validate_demo_records(records)
        with (upload_dir / "events.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

        dataset = existing or Dataset(
            name=f"{spec['name']} [SYNTHETIC DEMO]",
            version=version,
            file_path=str(upload_dir),
            status="uploaded",
            total_rows=len(records),
            uploaded_by=current_user.id if current_user.id > 0 else None,
            is_demo=True,
            schema_info={
                "source": "Synthetic demonstration data; not actual CERT data.",
                "generator_seed": spec["seed"],
                "available_activity_types": summary["activity_types"],
            },
        )
        if existing is None:
            db.add(dataset)
            db.commit()
            db.refresh(dataset)
    except IntegrityError:
        db.rollback()
        if existing is None:
            shutil.rmtree(upload_dir, ignore_errors=True)
            winner = db.scalar(select(Dataset).where(
                Dataset.is_demo.is_(True),
                Dataset.version == version,
            ))
            if winner is not None:
                if winner.status == "ready":
                    response.status_code = 200
                    return winner
                raise HTTPException(409, "This demo dataset is already being processed.")
        raise
    except Exception:
        db.rollback()
        if existing is None:
            shutil.rmtree(upload_dir, ignore_errors=True)
        raise

    background_tasks.add_task(ingest_dataset, dataset.id)
    return dataset


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    return db.query(Dataset).order_by(Dataset.created_at.desc()).all()


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds


@router.post("/{dataset_id}/reset-demo", response_model=DatasetOut)
def reset_demo_dataset(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found.")
    if not dataset.is_demo:
        raise HTTPException(400, "Only synthetic demo datasets can be reset.")
    if dataset.status in {"uploaded", "validating", "processing"}:
        raise HTTPException(409, "Wait for dataset preprocessing to finish before resetting it.")

    _delete_dataset_records(db, dataset_id)
    dataset.total_rows = 0
    dataset.valid_rows = 0
    dataset.unique_users = 0
    dataset.date_from = None
    dataset.date_to = None
    dataset.has_labels = False
    dataset.quality_report = None
    dataset.status = "uploaded"
    db.commit()
    background_tasks.add_task(ingest_dataset, dataset.id)
    return dataset


@router.get("/{dataset_id}/jobs", response_model=list[JobOut])
def get_jobs(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    return (
        db.query(ProcessingJob)
        .filter(ProcessingJob.dataset_id == dataset_id)
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    if ds.status in {"uploaded", "validating", "processing"}:
        raise HTTPException(409, "Wait for dataset preprocessing to finish before removing it.")
    if current_user.role != "admin" and not ds.is_demo and ds.uploaded_by != current_user.id:
        raise HTTPException(403, "Only an administrator or the dataset uploader can remove this dataset.")
    file_path = Path(ds.file_path).resolve()
    upload_root = UPLOAD_DIR.resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError:
        file_path = None

    _delete_dataset_records(db, dataset_id)
    db.delete(ds)
    db.commit()
    if file_path and file_path.exists():
        try:
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
        except OSError:
            logger.exception("Could not remove dataset files at %s", file_path)
            raise HTTPException(500, "Dataset records were removed, but uploaded files could not be deleted.")


def _delete_dataset_records(db: Session, dataset_id: int) -> None:
    alert_ids = select(Alert.id).where(Alert.dataset_id == dataset_id)
    db.execute(delete(BaselineUpdate).where(BaselineUpdate.dataset_id == dataset_id))
    db.execute(delete(DriftEvent).where(DriftEvent.dataset_id == dataset_id))
    db.execute(delete(ThresholdVersion).where(ThresholdVersion.dataset_id == dataset_id))
    db.execute(delete(AnalystReview).where(AnalystReview.alert_id.in_(alert_ids)))
    db.execute(delete(AlertEvidence).where(AlertEvidence.alert_id.in_(alert_ids)))
    db.execute(delete(Alert).where(Alert.dataset_id == dataset_id))
    db.execute(delete(RiskScore).where(RiskScore.dataset_id == dataset_id))
    db.execute(delete(BranchScore).where(BranchScore.dataset_id == dataset_id))
    db.execute(delete(ModelRun).where(ModelRun.dataset_id == dataset_id))
    db.execute(delete(ProcessingJob).where(ProcessingJob.dataset_id == dataset_id))
    db.execute(delete(UserProfile).where(UserProfile.dataset_id == dataset_id))
    db.execute(delete(ActivityEvent).where(ActivityEvent.dataset_id == dataset_id))
