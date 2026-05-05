import datetime
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
    now = datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(hours=24)

    # ── Devices ──────────────────────────────────────────────────────────────
    total_devices = (await db.execute(select(func.count(Device.id)))).scalar_one()

    active_rows = await db.execute(
        select(func.count(func.distinct(TelemetryEvent.device_id))).where(
            TelemetryEvent.received_at >= cutoff
        )
    )
    active_last_24h = active_rows.scalar_one()

    tier_rows = (
        await db.execute(
            select(Device.reward_tier, func.count(Device.id)).group_by(Device.reward_tier)
        )
    ).all()
    tier_distribution = [TierCount(tier=t.value, count=c) for t, c in tier_rows]

    # ── Ingestion ─────────────────────────────────────────────────────────────
    events_24h = (
        await db.execute(
            select(func.count(TelemetryEvent.id)).where(TelemetryEvent.received_at >= cutoff)
        )
    ).scalar_one()

    quarantined_24h = (
        await db.execute(
            select(func.count(QuarantineRecord.id)).where(QuarantineRecord.quarantined_at >= cutoff)
        )
    ).scalar_one()

    quarantine_rate = round(quarantined_24h / max(events_24h + quarantined_24h, 1) * 100, 2)

    # ── Recommendations ───────────────────────────────────────────────────────
    rec_24h = (
        await db.execute(
            select(func.count(RecommendationRequest.id)).where(
                RecommendationRequest.requested_at >= cutoff
            )
        )
    ).scalar_one()

    failed_24h = (
        await db.execute(
            select(func.count(RecommendationRequest.id))
            .where(RecommendationRequest.requested_at >= cutoff)
            .where(func.cardinality(RecommendationRequest.providers_succeeded) == 0)
        )
    ).scalar_one()

    # ── ML ────────────────────────────────────────────────────────────────────
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
            model_type=m.model_type.value,
            version=m.version,
            ndcg_at_10=m.ndcg_at_10,
            f1_score=m.f1_score,
        )
        for m in active_models_rows
    ]

    # ── Anomalies ─────────────────────────────────────────────────────────────
    detections_24h = (
        await db.execute(
            select(func.count(AnomalyReading.id)).where(AnomalyReading.reading_timestamp >= cutoff)
        )
    ).scalar_one()

    exceeded_24h = (
        await db.execute(
            select(func.count(AnomalyReading.id))
            .where(AnomalyReading.reading_timestamp >= cutoff)
            .where(AnomalyReading.threshold_exceeded.is_(True))
        )
    ).scalar_one()

    return SummaryReport(
        generated_at=now.isoformat(),
        devices=DeviceStats(
            total_devices=total_devices,
            active_last_24h=active_last_24h,
            tier_distribution=tier_distribution,
        ),
        ingestion=IngestionStats(
            events_last_24h=events_24h,
            quarantined_last_24h=quarantined_24h,
            quarantine_rate_pct=quarantine_rate,
        ),
        recommendations=RecommendationStats(
            requests_last_24h=rec_24h,
            failed_last_24h=failed_24h,
        ),
        ml=MLStats(
            last_training_status=last_job.status.value if last_job else None,
            last_training_at=last_job.started_at.isoformat() if last_job else None,
            active_models=active_models,
        ),
        anomalies=AnomalyStats(
            detections_last_24h=detections_24h,
            threshold_exceeded_last_24h=exceeded_24h,
        ),
    )
