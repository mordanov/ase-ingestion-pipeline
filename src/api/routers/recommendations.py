import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update

from src.api.dependencies import AppSettings, DbSession, ProviderAdapters
from src.credits.config_service import ConfigService
from src.credits.tier_engine import TierEngine
from src.db.models import Device
from src.db.models import RecommendationRequest as RecommendationRequestORM
from src.db.models.disabled_device import DisabledDevice
from src.db.models.telemetry import TelemetryEvent
from src.ml.anomaly_detector import ZScoreAnomalyDetector, apply_anomaly_suppression
from src.ml.feature_store import RedisFeatureStore
from src.ml.registry import DbModelRegistry
from src.ml.reranker import TFLiteReranker
from src.observability.logging import bind_trace_id, get_logger
from src.observability.metrics import (
    CREDIT_TIER_TOTAL,
    DEVICE_CREDIT_BALANCE,
    DEVICE_CREDITS_SPENT,
    ML_ANOMALY_REQUESTS_EVALUATED_TOTAL,
    ML_ANOMALY_SUPPRESSED_ITEMS_TOTAL,
    ML_INFERENCE_OUTCOME_TOTAL,
    ML_INFERENCE_P99_LATENCY_MS,
    RECOMMENDATION_DURATION_SECONDS,
    RECOMMENDATION_ERRORS_TOTAL,
    RECOMMENDATION_REQUESTS_TOTAL,
)
from src.recommendation.aggregator import AllProvidersFailedError, aggregate
from src.recommendation.delta_writer import DeltaRecommendationWriter, RecommendationRecord
from src.recommendation.models import (
    AllProvidersFailedResponse,
    InsufficientCreditsError,
    RecommendationItem,
    RecommendationResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recommendations"])


def _default_recommendation_items(items: list[Any]) -> list[RecommendationItem]:
    return [
        RecommendationItem(
            short_text=item.short_text,
            max_score=item.max_score,
            providers=item.providers,
            detail=item.detail,
        )
        for item in items
    ]


def _update_ml_inference_metrics(
    reranked: list[tuple[Any, float | None]], p99: float | None
) -> None:
    if p99 is not None:
        with suppress(Exception):
            ML_INFERENCE_P99_LATENCY_MS.set(p99)

    with suppress(Exception):
        has_scores = any(score is not None for _, score in reranked)
        outcome = "scored" if has_scores else "cold_start"
        ML_INFERENCE_OUTCOME_TOTAL.labels(outcome=outcome).inc()


def _record_anomaly_metrics(
    has_baseline: bool,
    suppressed_triples: list[tuple[Any, float | None, bool]],
) -> None:
    if not has_baseline:
        return

    with suppress(Exception):
        ML_ANOMALY_REQUESTS_EVALUATED_TOTAL.inc()
        suppressed_count = sum(1 for _, _, suppressed in suppressed_triples if suppressed)
        if suppressed_count:
            ML_ANOMALY_SUPPRESSED_ITEMS_TOTAL.inc(suppressed_count)


async def _get_device_or_404(db: DbSession, device_id: str) -> Device:
    device = (
        await db.execute(select(Device).where(Device.device_id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {device_id!r} not found")
    return device


async def _ensure_device_enabled(db: DbSession, device_id: str) -> None:
    if await db.scalar(select(DisabledDevice).where(DisabledDevice.device_id == device_id)):
        raise HTTPException(status_code=403, detail="DEVICE_DISABLED")


def _apply_credit_deduction(device: Device, credit_cost: int) -> tuple[int, int]:
    new_balance = device.credit_balance - credit_cost
    new_cumulative = device.cumulative_credits_spent + credit_cost
    return new_balance, new_cumulative


def _record_credit_metrics(
    device_id: str, credit_cost: int, new_balance: int, old_tier, new_tier
) -> None:
    with suppress(Exception):
        DEVICE_CREDITS_SPENT.labels(device_id=device_id).inc(credit_cost)
        DEVICE_CREDIT_BALANCE.labels(device_id=device_id).set(new_balance)
        if old_tier != new_tier:
            CREDIT_TIER_TOTAL.labels(tier=old_tier.value).dec()
            CREDIT_TIER_TOTAL.labels(tier=new_tier.value).inc()


async def _write_recommendation_delta(
    device_id: str,
    trace_id: str,
    agg_result: Any,
    recommendations_delta_dir: str,
) -> None:
    now = datetime.now(UTC)
    delta_writer = DeltaRecommendationWriter(recommendations_delta_dir)
    delta_records = [
        RecommendationRecord(
            trace_id=trace_id,
            device_id=device_id,
            provider_id=result.provider_id,
            recommendations=result.recommendations,
            requested_at=now,
        )
        for result in agg_result.raw_results
        if result.recommendations
    ]
    if delta_records:
        await delta_writer.write(delta_records)


async def _apply_ml_layer(device_id: str, items: list, db, settings) -> list[RecommendationItem]:
    """Apply ML re-ranking and anomaly suppression with full graceful fallback."""
    try:
        # Count telemetry days for cold-start detection
        cutoff = datetime.now(UTC) - timedelta(days=30)
        result = await db.execute(
            select(func.count(func.distinct(func.date(TelemetryEvent.event_timestamp))))
            .where(TelemetryEvent.device_id == device_id)
            .where(TelemetryEvent.event_timestamp >= cutoff)
        )
        telemetry_days = result.scalar_one() or 0

        registry = DbModelRegistry(db)
        feature_store = RedisFeatureStore(
            redis_url=settings.redis_url,
            ttl_seconds=settings.embedding_ttl_seconds,
        )
        reranker = TFLiteReranker(
            feature_store=feature_store,
            registry=registry,
            min_telemetry_days=settings.min_telemetry_days,
        )

        # Re-rank
        reranked = await reranker.rerank(device_id, items, telemetry_days)
        _update_ml_inference_metrics(reranked, reranker.get_p99_latency_ms())

        # Anomaly detection — use last known telemetry payload from DB
        anomaly_detector = ZScoreAnomalyDetector(
            db=db,
            threshold=settings.anomaly_threshold,
            min_baseline_days=settings.min_telemetry_days,
        )
        last_event = await db.execute(
            select(TelemetryEvent)
            .where(TelemetryEvent.device_id == device_id)
            .order_by(TelemetryEvent.received_at.desc())
            .limit(1)
        )
        last_event_row = last_event.scalar_one_or_none()
        reading = last_event_row.payload if last_event_row else {}
        anomaly_result = await anomaly_detector.detect(device_id, reading, telemetry_days)

        # Apply suppression
        suppressed_triples = apply_anomaly_suppression(
            [(item, score) for item, score in reranked],
            anomaly_result,
        )

        _record_anomaly_metrics(anomaly_result.has_baseline, suppressed_triples)

        return [
            RecommendationItem(
                short_text=item.short_text,
                max_score=item.max_score,
                providers=item.providers,
                detail=item.detail,
                personal_relevance_score=score,
                anomaly_suppressed=suppressed,
            )
            for item, score, suppressed in suppressed_triples
        ]

    except Exception as exc:
        logger.warning("ml_layer_fallback", device_id=device_id, error=str(exc))
        with suppress(Exception):
            ML_INFERENCE_OUTCOME_TOTAL.labels(outcome="fallback").inc()
        return _default_recommendation_items(items)


class RecommendationRequestBody(BaseModel):
    min_confidence: float = 0.2


@router.post(
    "/devices/{device_id}/recommendations",
    response_model=RecommendationResponse,
    responses={
        402: {"model": InsufficientCreditsError},
        503: {"model": AllProvidersFailedResponse},
    },
)
async def get_recommendations(
    device_id: str,
    db: DbSession,
    providers: ProviderAdapters,
    settings: AppSettings,
    body: RecommendationRequestBody | None = Body(default=None),  # noqa: B008
) -> Any:
    trace_id = str(uuid.uuid4().hex)
    bind_trace_id(trace_id)

    device = await _get_device_or_404(db, device_id)
    await _ensure_device_enabled(db, device_id)

    credit_config = await ConfigService(db).get_active()
    credit_cost = credit_config.service_costs.get("default", 1)

    if device.credit_balance < credit_cost:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credits",
        )

    min_score = (body.min_confidence if body else RecommendationRequestBody().min_confidence) * 1000

    start_time = monotonic()
    RECOMMENDATION_REQUESTS_TOTAL.labels(provider_count=str(len(providers))).inc()

    try:
        agg_result = await aggregate(
            providers,
            height_cm=device.height_cm,
            weight_kg=device.weight_kg,
            timeout=settings.recommendation_timeout_seconds,
            min_score=min_score,
        )
    except AllProvidersFailedError as exc:
        RECOMMENDATION_ERRORS_TOTAL.labels(reason="all_providers_failed").inc()
        RECOMMENDATION_DURATION_SECONDS.observe(monotonic() - start_time)
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "All recommendation providers failed or timed out",
                "trace_id": trace_id,
                "providers_attempted": exc.providers,
                "duration_ms": exc.duration_ms,
            },
        ) from exc

    RECOMMENDATION_DURATION_SECONDS.observe(monotonic() - start_time)

    # Deduct credit and update tier
    new_balance, new_cumulative = _apply_credit_deduction(device, credit_cost)
    tier_engine = TierEngine()
    old_tier = device.reward_tier
    new_tier = tier_engine.compute_tier(new_cumulative)

    await db.execute(
        update(Device)
        .where(Device.device_id == device_id)
        .values(
            credit_balance=new_balance,
            cumulative_credits_spent=new_cumulative,
            reward_tier=new_tier,
        )
    )

    _record_credit_metrics(device_id, credit_cost, new_balance, old_tier, new_tier)

    # Write raw per-provider recommendations to Delta Lake
    await _write_recommendation_delta(
        device_id=device_id,
        trace_id=trace_id,
        agg_result=agg_result,
        recommendations_delta_dir=settings.recommendations_delta_dir,
    )

    # Persist recommendation request
    req = RecommendationRequestORM(
        id=uuid.uuid4(),
        device_id=device_id,
        trace_id=trace_id,
        height_cm=device.height_cm,
        weight_kg=device.weight_kg,
        providers_called=agg_result.providers_called,
        providers_succeeded=agg_result.providers_succeeded,
        result={"recommendations": [r.__dict__ for r in agg_result.recommendations]},
        duration_ms=agg_result.duration_ms,
        requested_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(req)
    await db.commit()

    # Apply ML re-ranking and anomaly detection (falls back gracefully if unavailable)
    recommendations = await _apply_ml_layer(
        device_id=device_id,
        items=agg_result.recommendations,
        db=db,
        settings=settings,
    )

    return RecommendationResponse(
        device_id=device_id,
        trace_id=trace_id,
        recommendations=recommendations,
        providers_called=agg_result.providers_called,
        providers_succeeded=agg_result.providers_succeeded,
        duration_ms=agg_result.duration_ms,
        credits_remaining=new_balance,
        reward_tier=new_tier.value,
    )
