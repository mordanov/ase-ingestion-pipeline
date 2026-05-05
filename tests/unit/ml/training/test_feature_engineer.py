"""Unit tests for FeatureEngineer — T032 (must FAIL before implementation)."""
import struct

import pytest

from src.ml.training.data_extractor import TelemetryRecord
from src.ml.training.feature_engineer import FeatureEngineer, _EMBEDDING_DIM


def _make_record(device_id: str, day: str, heart_rate: float = 72.0) -> TelemetryRecord:
    return TelemetryRecord(
        device_id=device_id,
        event_timestamp=f"{day}T10:00:00Z",
        heart_rate=heart_rate,
        steps=8000.0,
        sleep_duration=7.5,
        activity_level="moderate",
    )


@pytest.fixture
def engineer():
    return FeatureEngineer(min_days=7, embedding_dim=_EMBEDDING_DIM)


def _make_7_days(device_id: str) -> list[TelemetryRecord]:
    return [_make_record(device_id, f"2026-04-{15 + i:02d}") for i in range(7)]


def test_produces_correct_dim(engineer):
    records = _make_7_days("dev-1")
    features = engineer.build_features(records)
    assert len(features) == 1
    vec_floats = struct.unpack(f"{_EMBEDDING_DIM}f", features[0].vector)
    assert len(vec_floats) == _EMBEDDING_DIM


def test_excludes_devices_below_min_days(engineer):
    records = [_make_record("dev-short", "2026-04-15")]  # only 1 day
    features = engineer.build_features(records)
    assert len(features) == 0


def test_includes_devices_at_exactly_min_days(engineer):
    records = _make_7_days("dev-7days")
    features = engineer.build_features(records)
    assert len(features) == 1
    assert features[0].telemetry_days == 7


def test_multiple_devices_independent(engineer):
    records = _make_7_days("dev-a") + _make_7_days("dev-b")
    features = engineer.build_features(records)
    assert len(features) == 2
    device_ids = {f.device_id for f in features}
    assert device_ids == {"dev-a", "dev-b"}


def test_handles_missing_telemetry_fields(engineer):
    records = [
        TelemetryRecord(
            device_id="dev-sparse",
            event_timestamp=f"2026-04-{15 + i:02d}T10:00:00Z",
            heart_rate=None,
            steps=None,
            sleep_duration=None,
            activity_level=None,
        )
        for i in range(7)
    ]
    # Should not raise; device may produce zero vector
    features = engineer.build_features(records)
    assert len(features) == 1  # still included if 7 days present
    assert len(features[0].vector) == _EMBEDDING_DIM * 4  # bytes


def test_sample_count_reflects_record_count(engineer):
    records = _make_7_days("dev-1") * 3  # 21 records across 7 days
    features = engineer.build_features(records)
    assert len(features) == 1
    assert features[0].sample_count == 21
