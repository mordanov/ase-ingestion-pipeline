"""Unit tests for src/ingestion/validator.py"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ingestion.interfaces import IngestionEvent, SourceProtocol


def _make_event(**overrides) -> IngestionEvent:
    defaults = dict(
        device_id="dev-001",
        event_id="evt-abc",
        source_protocol=SourceProtocol.HTTP,
        event_timestamp=datetime.now(timezone.utc),
        payload={"heart_rate": {"bpm": 72}},
        trace_id="trace-xyz",
        is_batch=False,
        batch_id=None,
    )
    defaults.update(overrides)
    return IngestionEvent(**defaults)


@pytest.mark.asyncio
async def test_valid_event_passes():
    from src.ingestion.validator import ValidationError, validate_event

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="dev-001")))

    event = _make_event()
    result = await validate_event(event, session)
    assert result.is_valid
    assert not result.is_stale


@pytest.mark.asyncio
async def test_missing_device_id_raises():
    from src.ingestion.validator import ValidationError, validate_event

    event = _make_event(device_id="")
    session = AsyncMock()

    with pytest.raises(ValidationError, match="device_id"):
        await validate_event(event, session)


@pytest.mark.asyncio
async def test_stale_timestamp_sets_flag():
    from src.ingestion.validator import validate_event

    old_ts = datetime.now(timezone.utc) - timedelta(hours=25)
    event = _make_event(event_timestamp=old_ts)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="dev-001")))

    result = await validate_event(event, session)
    assert result.is_stale


@pytest.mark.asyncio
async def test_anomaly_flag_passthrough():
    from src.ingestion.validator import validate_event

    event = _make_event(payload={"is_anomaly": True, "heart_rate": {"bpm": 220}})
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="dev-001")))

    result = await validate_event(event, session)
    assert result.is_valid


@pytest.mark.asyncio
async def test_unknown_device_quarantines():
    from src.ingestion.validator import validate_event

    event = _make_event(device_id="unknown-device-xyz")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await validate_event(event, session)
    assert not result.is_valid
    assert result.error_code == "UNKNOWN_DEVICE"
