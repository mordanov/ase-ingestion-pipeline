"""Integration tests for POST /ingest endpoint (T017)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from tests.conftest import make_telemetry_event


@pytest.mark.asyncio
async def test_ingest_single_event_accepted(async_client: AsyncClient, seeded_device):
    payload = make_telemetry_event(seeded_device.device_id)

    resp = await async_client.post("/ingest", json=payload)

    assert resp.status_code == 202
    data = resp.json()
    assert data["accepted"] == 1
    assert data["quarantined"] == 0
    assert "trace_id" in data


@pytest.mark.asyncio
async def test_ingest_batch_accepted(async_client: AsyncClient, seeded_device):
    events = [make_telemetry_event(seeded_device.device_id) for _ in range(3)]
    batch = {
        "batch_id": str(uuid.uuid4()),
        "sent_at": datetime.now(UTC).isoformat(),
        "event_count": 3,
        "events": events,
    }

    resp = await async_client.post("/ingest", json=batch)

    assert resp.status_code == 202
    data = resp.json()
    assert data["accepted"] == 3
    assert data["quarantined"] == 0


@pytest.mark.asyncio
async def test_ingest_missing_device_id_quarantines(async_client: AsyncClient):
    payload = make_telemetry_event(device_id="")  # no device_id

    resp = await async_client.post("/ingest", json=payload)

    assert resp.status_code in (202, 422)
    data = resp.json()
    assert data["quarantined"] >= 1
    assert data["accepted"] == 0


@pytest.mark.asyncio
async def test_ingest_unknown_device_quarantines(async_client: AsyncClient):
    payload = make_telemetry_event("nonexistent-device-xyz")

    resp = await async_client.post("/ingest", json=payload)

    assert resp.status_code in (202, 422)
    data = resp.json()
    assert data["quarantined"] >= 1


@pytest.mark.asyncio
async def test_ingest_duplicate_event_id_not_quarantined(async_client: AsyncClient, seeded_device):
    """Duplicate event_id should be silently accepted (idempotent), not quarantined."""
    event = make_telemetry_event(seeded_device.device_id)

    resp1 = await async_client.post("/ingest", json=event)
    assert resp1.status_code == 202

    resp2 = await async_client.post("/ingest", json=event)
    assert resp2.status_code == 202
    data = resp2.json()
    assert data["accepted"] == 0
    assert data["quarantined"] == 0


@pytest.mark.asyncio
async def test_ingest_event_persisted_in_db(async_client: AsyncClient, seeded_device, db_session):
    from sqlalchemy import select
    from src.db.models import TelemetryEvent

    payload = make_telemetry_event(seeded_device.device_id)
    event_id = payload["event_id"]

    resp = await async_client.post("/ingest", json=payload)
    assert resp.status_code == 202

    result = await db_session.execute(
        select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.device_id == seeded_device.device_id
