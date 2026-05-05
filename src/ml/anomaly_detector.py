import math
import uuid
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.ml_anomaly_reading import AnomalyReading
from src.ml.interfaces import AnomalyDetector, AnomalyResult
from src.observability.logging import get_logger
from src.observability.tracing import get_tracer

logger = get_logger(__name__)
_tracer = get_tracer("ml.anomaly_detector")

_ACTIVITY_INTENSIFICATION_TERMS = frozenset(
    ["exercise", "run", "workout", "activity", "steps", "intensity", "cardio", "training", "jog"]
)
_BASELINE_FEATURES = ("heart_rate", "steps", "sleep_duration")


class ZScoreAnomalyDetector(AnomalyDetector):
    """Per-user Z-score anomaly detector backed by PostgreSQL AnomalyReading history."""

    def __init__(self, db: AsyncSession, threshold: float = 0.5, min_baseline_days: int = 7):
        self._db = db
        self._threshold = threshold
        self._min_baseline_days = min_baseline_days

    async def detect(self, device_id: str, reading: dict, baseline_days: int) -> AnomalyResult:
        """Compute anomaly score for the given reading against the device's personal baseline.

        Returns AnomalyResult with has_baseline=False when device has insufficient history (FR-008).
        """
        start = monotonic()
        with _tracer.start_as_current_span("ml.anomaly_detector.detect") as span:
            span.set_attribute("device_id", device_id)
            span.set_attribute("baseline_days", baseline_days)

            if baseline_days < self._min_baseline_days:
                span.set_attribute("outcome", "no_baseline")
                return AnomalyResult(
                    anomaly_score=0.0, threshold_exceeded=False, has_baseline=False
                )

            stats = await self._compute_baseline_stats(device_id)
            if not stats:
                span.set_attribute("outcome", "insufficient_history")
                return AnomalyResult(
                    anomaly_score=0.0, threshold_exceeded=False, has_baseline=False
                )

            score = self._compute_zscore(reading, stats)
            exceeded = score > self._threshold

            span.set_attribute("anomaly_score", score)
            span.set_attribute("threshold_exceeded", exceeded)

            await self._persist_reading(device_id, reading, score, exceeded)

            elapsed_ms = (monotonic() - start) * 1000
            logger.debug(
                "anomaly_detected",
                device_id=device_id,
                score=score,
                threshold_exceeded=exceeded,
                duration_ms=round(elapsed_ms, 2),
            )
            return AnomalyResult(
                anomaly_score=score, threshold_exceeded=exceeded, has_baseline=True
            )

    async def _compute_baseline_stats(self, device_id: str) -> dict | None:
        """Load per-feature mean/std from recent AnomalyReading history."""
        readings = await self._load_recent_readings(device_id)
        if len(readings) < 10:
            return None

        stats: dict[str, dict[str, float]] = {}
        for feature in _BASELINE_FEATURES:
            values = self._feature_values(readings, feature)
            if len(values) >= 5:
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                stats[feature] = {"mean": mean, "std": math.sqrt(variance) + 1e-6}
        return stats if stats else None

    async def _load_recent_readings(self, device_id: str) -> list[AnomalyReading]:
        result = await self._db.execute(
            select(AnomalyReading)
            .where(AnomalyReading.device_id == device_id)
            .order_by(AnomalyReading.reading_timestamp.desc())
            .limit(200)
        )
        return result.scalars().all()

    @staticmethod
    def _feature_values(readings: list[AnomalyReading], feature: str) -> list[float]:
        values: list[float] = []
        for reading in readings:
            value = (reading.evaluated_fields or {}).get(feature)
            if value is not None:
                values.append(float(value))
        return values

    def _compute_zscore(self, reading: dict[str, Any], stats: dict[str, dict[str, float]]) -> float:
        """Max normalised deviation across evaluated features, mapped to [0, 1] via sigmoid."""
        z_scores = []
        for feature, feature_stats in stats.items():
            val = reading.get(feature)
            if val is not None:
                z = abs((float(val) - feature_stats["mean"]) / feature_stats["std"])
                z_scores.append(z)
        if not z_scores:
            return 0.0
        max_z = max(z_scores)
        # Sigmoid of (max_z - 2): score ~0.5 at 2σ deviation, ~0.88 at 4σ
        return _sigmoid(max_z - 2.0)

    async def _persist_reading(
        self, device_id: str, reading: dict, score: float, exceeded: bool
    ) -> None:
        evaluated = {
            feature: reading.get(feature) for feature in _BASELINE_FEATURES if feature in reading
        }
        record = AnomalyReading(
            id=uuid.uuid4(),
            device_id=device_id,
            reading_timestamp=datetime.now(UTC),
            anomaly_score=score,
            threshold_exceeded=exceeded,
            evaluated_fields=evaluated,
            suppression_threshold=self._threshold,
        )
        self._db.add(record)
        try:
            await self._db.flush()
        except Exception as exc:
            logger.warning("anomaly_reading_persist_failed", error=str(exc))


def is_activity_intensification(short_text: str) -> bool:
    """Return True if the recommendation is an activity-intensification item."""
    lower = short_text.lower()
    return any(term in lower for term in _ACTIVITY_INTENSIFICATION_TERMS)


def apply_anomaly_suppression(
    items_with_scores: list,
    anomaly_result: AnomalyResult,
) -> list:
    """Apply anomaly suppression to re-ranked (item, score) pairs.

    Suppresses activity-intensification items when threshold is exceeded (FR-006).
    Always retains at least one item (FR-007).
    """
    if not anomaly_result.has_baseline or not anomaly_result.threshold_exceeded:
        return [(item, score, False) for item, score in items_with_scores]

    suppressed = []
    kept = []
    for item, score in items_with_scores:
        if is_activity_intensification(getattr(item, "short_text", str(item))):
            suppressed.append((item, score, True))
        else:
            kept.append((item, score, False))

    result = list(kept)
    result += suppressed  # suppressed items appended last with flag True

    # At-least-one guarantee (FR-007): if everything was suppressed, keep the first item
    if not kept and suppressed:
        first_item, first_score, _ = suppressed[0]
        result = [(first_item, first_score, False)] + [(i, s, True) for i, s, _ in suppressed[1:]]

    return result


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0
