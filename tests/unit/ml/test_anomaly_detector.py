"""Unit tests for ZScoreAnomalyDetector — T020 (must FAIL before implementation)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ml.anomaly_detector import (
    ZScoreAnomalyDetector,
    apply_anomaly_suppression,
    is_activity_intensification,
)
from src.ml.interfaces import AnomalyResult
from src.recommendation.normalizer import AggregatedRecommendation


def _make_item(text: str, score: float = 500.0) -> AggregatedRecommendation:
    return AggregatedRecommendation(short_text=text, max_score=score, providers=["s1"])


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def detector(mock_db):
    return ZScoreAnomalyDetector(db=mock_db, threshold=0.5, min_baseline_days=7)


@pytest.mark.asyncio
async def test_no_baseline_user_returns_no_flag(detector):
    """Users with < 7 days of history receive no anomaly flag (FR-008)."""
    result = await detector.detect("new-dev", {"heart_rate": 180}, baseline_days=3)
    assert result.has_baseline is False
    assert result.threshold_exceeded is False
    assert result.anomaly_score == 0.0


@pytest.mark.asyncio
async def test_insufficient_readings_returns_no_baseline(mock_db, detector):
    """Fewer than 10 historical readings → no baseline established."""

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    result = await detector.detect("sparse-dev", {"heart_rate": 75}, baseline_days=14)
    assert result.has_baseline is False


@pytest.mark.asyncio
async def test_within_baseline_low_score(mock_db, detector):
    """Reading within personal baseline produces a low anomaly score (< threshold)."""
    from src.db.models.ml_anomaly_reading import AnomalyReading

    # Simulate 20 readings around heart_rate=75 (normal baseline)
    def make_reading(hr: float):
        r = MagicMock(spec=AnomalyReading)
        r.evaluated_fields = {"heart_rate": hr, "steps": 8000, "sleep_duration": 7.5}
        return r

    readings = [make_reading(75.0 + (i % 5 - 2)) for i in range(20)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = readings
    mock_db.execute.return_value = mock_result

    result = await detector.detect("norm-dev", {"heart_rate": 76}, baseline_days=14)
    assert result.has_baseline is True
    assert result.anomaly_score < 0.5


@pytest.mark.asyncio
async def test_anomalous_reading_exceeds_threshold(mock_db, detector):
    """Heart rate significantly above baseline produces score > threshold."""
    from src.db.models.ml_anomaly_reading import AnomalyReading

    def make_reading(hr: float):
        r = MagicMock(spec=AnomalyReading)
        r.evaluated_fields = {"heart_rate": hr, "steps": 8000, "sleep_duration": 7.5}
        return r

    readings = [make_reading(72.0 + (i % 3)) for i in range(20)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = readings
    mock_db.execute.return_value = mock_result

    result = await detector.detect("norm-dev", {"heart_rate": 195}, baseline_days=14)
    assert result.has_baseline is True
    assert result.threshold_exceeded is True
    assert result.anomaly_score > 0.5


def test_is_activity_intensification():
    assert is_activity_intensification("Go for a run today") is True
    assert is_activity_intensification("Try a workout") is True
    assert is_activity_intensification("Increase activity level") is True
    assert is_activity_intensification("Drink more water") is False
    assert is_activity_intensification("Sleep 8 hours") is False


def test_apply_suppression_no_anomaly():
    items = [(_make_item("Go for a run"), 0.9), (_make_item("Drink water"), 0.8)]
    result_no_anomaly = apply_anomaly_suppression(
        items, AnomalyResult(anomaly_score=0.3, threshold_exceeded=False, has_baseline=True)
    )
    # No suppression when threshold not exceeded
    assert all(not suppressed for _, _, suppressed in result_no_anomaly)


def test_apply_suppression_suppresses_intensification():
    items = [
        (_make_item("Go for a run"), 0.9),
        (_make_item("Increase steps target"), 0.8),
        (_make_item("Drink more water"), 0.7),
        (_make_item("Get more sleep"), 0.6),
    ]
    result = apply_anomaly_suppression(
        items, AnomalyResult(anomaly_score=0.8, threshold_exceeded=True, has_baseline=True)
    )
    suppressed_texts = {item.short_text for item, _, suppressed in result if suppressed}
    assert "Go for a run" in suppressed_texts
    assert "Increase steps target" in suppressed_texts
    kept_texts = {item.short_text for item, _, suppressed in result if not suppressed}
    assert "Drink more water" in kept_texts


def test_at_least_one_guarantee():
    """All items are activity-intensification — at least one must be returned (FR-007)."""
    items = [
        (_make_item("Go for a run"), 0.9),
        (_make_item("Workout more"), 0.8),
    ]
    result = apply_anomaly_suppression(
        items, AnomalyResult(anomaly_score=0.9, threshold_exceeded=True, has_baseline=True)
    )
    # At least one item should be kept (not suppressed)
    kept = [item for item, _, suppressed in result if not suppressed]
    assert len(kept) >= 1
