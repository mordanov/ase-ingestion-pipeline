import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import AppSettings, DbSession
from src.db.models.ml_on_device_package import OnDeviceModelPackage
from src.db.models.ml_training_job import TrainingJob, TrainingJobStatus
from src.observability.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/admin/ml", tags=["ml-training"])


# ── Pydantic models ──────────────────────────────────────────────────────────


class RetrainResponse(BaseModel):
    job_id: str
    status: str
    triggered_by: str
    started_at: str


class TrainingJobResponse(BaseModel):
    job_id: str
    status: str
    triggered_by: str
    started_at: str
    ended_at: str | None
    reranker_ndcg_at_10: float | None
    anomaly_detector_f1: float | None
    error_message: str | None


class PackageMetaResponse(BaseModel):
    package_id: str
    reranker_version: int
    anomaly_detector_version: int
    created_at: str
    download_url: str
    size_bytes: int | None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/retrain", response_model=RetrainResponse, status_code=202)
async def retrain_models(db: DbSession, settings: AppSettings) -> Any:
    """Initiate the full ML training pipeline (FR-015). Rejects concurrent runs (FR-016)."""
    from src.ml.training.pipeline import TrainingAlreadyRunningError, TrainingPipeline

    # Check for running job before starting
    existing = (
        await db.execute(select(TrainingJob).where(TrainingJob.status == TrainingJobStatus.running))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Training already in progress",
                "active_job_id": str(existing.id),
            },
        )

    pipeline = TrainingPipeline(
        db=db,
        telemetry_dir=settings.delta_output_dir,
        recommendations_dir=settings.recommendations_delta_dir,
        artifact_dir=settings.model_artifact_dir,
        package_dir=settings.on_device_package_dir,
        min_telemetry_days=settings.min_telemetry_days,
    )

    async def _run_pipeline():
        try:
            await pipeline.run(triggered_by="admin")
        except TrainingAlreadyRunningError:
            pass
        except Exception as exc:
            logger.error("background_training_failed", error=str(exc))

    try:
        job = await pipeline.run(triggered_by="admin")
        return RetrainResponse(
            job_id=str(job.id),
            status=job.status.value,
            triggered_by=job.triggered_by,
            started_at=job.started_at.isoformat(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/training-jobs/{job_id}", response_model=TrainingJobResponse)
async def get_training_job(job_id: UUID, db: DbSession) -> Any:
    result = await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Training job not found")

    return TrainingJobResponse(
        job_id=str(job.id),
        status=job.status.value,
        triggered_by=job.triggered_by,
        started_at=job.started_at.isoformat(),
        ended_at=job.ended_at.isoformat() if job.ended_at else None,
        reranker_ndcg_at_10=job.reranker_ndcg_at_10,
        anomaly_detector_f1=job.anomaly_detector_f1,
        error_message=job.error_message,
    )


@router.get("/model-package/latest", response_model=PackageMetaResponse)
async def get_latest_package(db: DbSession) -> Any:
    result = await db.execute(
        select(OnDeviceModelPackage).order_by(OnDeviceModelPackage.created_at.desc()).limit(1)
    )
    pkg = result.scalar_one_or_none()
    if pkg is None:
        raise HTTPException(status_code=404, detail="No model package has been built yet")

    size = None
    if os.path.exists(pkg.package_path):
        size = os.path.getsize(pkg.package_path)

    return PackageMetaResponse(
        package_id=str(pkg.id),
        reranker_version=pkg.reranker_model_id,
        anomaly_detector_version=pkg.anomaly_detector_model_id,
        created_at=pkg.created_at.isoformat(),
        download_url=f"/admin/ml/model-package/{pkg.id}/download",
        size_bytes=size,
    )


@router.get("/model-package/{package_id}/download")
async def download_package(package_id: UUID, db: DbSession) -> Any:
    result = await db.execute(
        select(OnDeviceModelPackage).where(OnDeviceModelPackage.id == package_id)
    )
    pkg = result.scalar_one_or_none()
    if pkg is None:
        raise HTTPException(status_code=404, detail="Package not found")

    if not os.path.exists(pkg.package_path):
        raise HTTPException(status_code=404, detail="Package file not found on disk")

    filename = os.path.basename(pkg.package_path)
    return FileResponse(
        pkg.package_path,
        media_type="application/zip",
        filename=filename,
    )
