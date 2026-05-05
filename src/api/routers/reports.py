from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from src.api.dependencies import AppSettings, DbSession
from src.db.models.device import Device
from src.db.models.ml_anomaly_reading import AnomalyReading
from src.db.models.ml_trained_model import ModelDeploymentStatus, TrainedModel
from src.db.models.ml_training_job import TrainingJob
from src.db.models.quarantine import QuarantineRecord
from src.db.models.recommendation import RecommendationRequest
from src.db.models.telemetry import TelemetryEvent

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


async def _count_scalar(db: DbSession, statement) -> int:
    return (await db.execute(statement)).scalar_one()


async def _build_device_stats(db: DbSession, cutoff: datetime) -> DeviceStats:
    total_devices = await _count_scalar(db, select(func.count(Device.id)))
    active_last_24h = await _count_scalar(
        db,
        select(func.count(func.distinct(TelemetryEvent.device_id))).where(
            TelemetryEvent.received_at >= cutoff
        ),
    )
    tier_rows = (
        await db.execute(
            select(Device.reward_tier, func.count(Device.id)).group_by(Device.reward_tier)
        )
    ).all()
    return DeviceStats(
        total_devices=total_devices,
        active_last_24h=active_last_24h,
        tier_distribution=[TierCount(tier=tier.value, count=count) for tier, count in tier_rows],
    )


async def _build_ingestion_stats(db: DbSession, cutoff: datetime) -> IngestionStats:
    events_last_24h = await _count_scalar(
        db,
        select(func.count(TelemetryEvent.id)).where(TelemetryEvent.received_at >= cutoff),
    )
    quarantined_last_24h = await _count_scalar(
        db,
        select(func.count(QuarantineRecord.id)).where(QuarantineRecord.quarantined_at >= cutoff),
    )
    quarantine_rate = round(
        quarantined_last_24h / max(events_last_24h + quarantined_last_24h, 1) * 100,
        2,
    )
    return IngestionStats(
        events_last_24h=events_last_24h,
        quarantined_last_24h=quarantined_last_24h,
        quarantine_rate_pct=quarantine_rate,
    )


async def _build_recommendation_stats(db: DbSession, cutoff: datetime) -> RecommendationStats:
    requests_last_24h = await _count_scalar(
        db,
        select(func.count(RecommendationRequest.id)).where(
            RecommendationRequest.requested_at >= cutoff
        ),
    )
    failed_last_24h = await _count_scalar(
        db,
        select(func.count(RecommendationRequest.id))
        .where(RecommendationRequest.requested_at >= cutoff)
        .where(func.cardinality(RecommendationRequest.providers_succeeded) == 0),
    )
    return RecommendationStats(
        requests_last_24h=requests_last_24h,
        failed_last_24h=failed_last_24h,
    )


async def _build_ml_stats(db: DbSession) -> MLStats:
    last_job = (
        await db.execute(select(TrainingJob).order_by(TrainingJob.started_at.desc()).limit(1))
    ).scalar_one_or_none()
    active_models_rows = (
        (
            await db.execute(
                select(TrainedModel).where(
                    TrainedModel.deployment_status == ModelDeploymentStatus.active
                )
            )
        )
        .scalars()
        .all()
    )
    active_models = [
        MLModelInfo(
            model_type=model.model_type.value,
            version=model.version,
            ndcg_at_10=model.ndcg_at_10,
            f1_score=model.f1_score,
        )
        for model in active_models_rows
    ]
    return MLStats(
        last_training_status=last_job.status.value if last_job else None,
        last_training_at=last_job.started_at.isoformat() if last_job else None,
        active_models=active_models,
    )


async def _build_anomaly_stats(db: DbSession, cutoff: datetime) -> AnomalyStats:
    detections_last_24h = await _count_scalar(
        db,
        select(func.count(AnomalyReading.id)).where(AnomalyReading.reading_timestamp >= cutoff),
    )
    threshold_exceeded_last_24h = await _count_scalar(
        db,
        select(func.count(AnomalyReading.id))
        .where(AnomalyReading.reading_timestamp >= cutoff)
        .where(AnomalyReading.threshold_exceeded.is_(True)),
    )
    return AnomalyStats(
        detections_last_24h=detections_last_24h,
        threshold_exceeded_last_24h=threshold_exceeded_last_24h,
    )


class TierCount(BaseModel):
    tier: str
    count: int


class DeviceStats(BaseModel):
    total_devices: int
    active_last_24h: int
    tier_distribution: list[TierCount]


class IngestionStats(BaseModel):
    events_last_24h: int
    quarantined_last_24h: int
    quarantine_rate_pct: float


class RecommendationStats(BaseModel):
    requests_last_24h: int
    failed_last_24h: int


class MLModelInfo(BaseModel):
    model_type: str
    version: int
    ndcg_at_10: float | None
    f1_score: float | None


class MLStats(BaseModel):
    last_training_status: str | None
    last_training_at: str | None
    active_models: list[MLModelInfo]


class AnomalyStats(BaseModel):
    detections_last_24h: int
    threshold_exceeded_last_24h: int


class SummaryReport(BaseModel):
    generated_at: str
    devices: DeviceStats
    ingestion: IngestionStats
    recommendations: RecommendationStats
    ml: MLStats
    anomalies: AnomalyStats


@router.get("/summary", response_model=SummaryReport)
async def get_summary_report(db: DbSession, settings: AppSettings) -> Any:
    """Platform health and compliance summary report."""
    _ = settings  # reserved for future report parameterization
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=24)

    devices = await _build_device_stats(db, cutoff)
    ingestion = await _build_ingestion_stats(db, cutoff)
    recommendations = await _build_recommendation_stats(db, cutoff)
    ml = await _build_ml_stats(db)
    anomalies = await _build_anomaly_stats(db, cutoff)

    return SummaryReport(
        generated_at=now.isoformat(),
        devices=devices,
        ingestion=ingestion,
        recommendations=recommendations,
        ml=ml,
        anomalies=anomalies,
    )
