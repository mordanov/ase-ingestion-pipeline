from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import AppSettings, DbSession
from src.db.models.ml_trained_model import ModelDeploymentStatus, ModelType, TrainedModel
from src.db.models.ml_training_job import TrainingJob, TrainingJobStatus

router = APIRouter(prefix="/admin/ml", tags=["ml-metrics"])


# ── Pydantic models ──────────────────────────────────────────────────────────


class ModelMetrics(BaseModel):
    model_version: int | None
    ndcg_at_10: float | None = None
    f1_score: float | None = None
    deployment_status: str
    deployed_at: str | None


class InferenceMetrics(BaseModel):
    p99_latency_ms: float | None
    window_seconds: int = 300


class StalenessMetrics(BaseModel):
    last_trained_at: str | None
    elapsed_seconds: int | None
    threshold_seconds: int


class MLMetricsResponse(BaseModel):
    reranker: ModelMetrics
    anomaly_detector: ModelMetrics
    inference: InferenceMetrics
    staleness: StalenessMetrics


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.get("/metrics", response_model=MLMetricsResponse)
async def get_ml_metrics(db: DbSession, settings: AppSettings) -> Any:
    """Return all four ML monitoring metrics (FR-018)."""

    reranker_model = await _get_active(db, ModelType.reranker)
    anomaly_model = await _get_active(db, ModelType.anomaly_detector)

    last_job = await _get_last_succeeded_job(db)
    last_trained_at = last_job.ended_at if last_job else None
    elapsed: int | None = None
    if last_trained_at is not None:
        import datetime

        elapsed = int((datetime.datetime.now(datetime.UTC) - last_trained_at).total_seconds())

    # Read p99 from Prometheus gauge (updated by reranker after each inference)
    p99 = _read_p99_gauge()

    return MLMetricsResponse(
        reranker=ModelMetrics(
            model_version=reranker_model.version if reranker_model else None,
            ndcg_at_10=reranker_model.ndcg_at_10 if reranker_model else None,
            deployment_status=reranker_model.deployment_status.value if reranker_model else "none",
            deployed_at=reranker_model.deployed_at.isoformat()
            if reranker_model and reranker_model.deployed_at
            else None,
        ),
        anomaly_detector=ModelMetrics(
            model_version=anomaly_model.version if anomaly_model else None,
            f1_score=anomaly_model.f1_score if anomaly_model else None,
            deployment_status=anomaly_model.deployment_status.value if anomaly_model else "none",
            deployed_at=anomaly_model.deployed_at.isoformat()
            if anomaly_model and anomaly_model.deployed_at
            else None,
        ),
        inference=InferenceMetrics(p99_latency_ms=p99),
        staleness=StalenessMetrics(
            last_trained_at=last_trained_at.isoformat() if last_trained_at else None,
            elapsed_seconds=elapsed,
            threshold_seconds=settings.staleness_threshold_hours * 3600,
        ),
    )


async def _get_active(db, model_type: ModelType) -> TrainedModel | None:
    result = await db.execute(
        select(TrainedModel).where(
            TrainedModel.model_type == model_type,
            TrainedModel.deployment_status == ModelDeploymentStatus.active,
        )
    )
    return result.scalar_one_or_none()


async def _get_last_succeeded_job(db) -> TrainingJob | None:
    result = await db.execute(
        select(TrainingJob)
        .where(TrainingJob.status == TrainingJobStatus.succeeded)
        .order_by(TrainingJob.ended_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _read_p99_gauge() -> float | None:
    try:
        from src.observability.metrics import ML_INFERENCE_P99_LATENCY_MS

        samples = list(ML_INFERENCE_P99_LATENCY_MS.collect())
        for family in samples:
            for sample in family.samples:
                if sample.value > 0:
                    return sample.value
        return None
    except Exception:
        return None
