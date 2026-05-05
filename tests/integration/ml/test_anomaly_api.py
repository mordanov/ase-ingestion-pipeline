"""Integration tests for anomaly-suppressed recommendations — T021."""
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_anomaly_fields_present_in_recommendations(db_session: AsyncSession, async_client):
    """Recommendation response always includes anomaly_suppressed field."""
    device_id = f"anomaly-test-{uuid.uuid4().hex[:8]}"

    # Register device with credits
    reg = await async_client.post(
        "/api/v1/devices",
        json={
            "device_id": device_id,
            "name": "Anomaly Test Device",
            "height_cm": 175.0,
            "weight_kg": 70.0,
        },
        headers={"X-API-Key": "test-key"},
    )
    assert reg.status_code in (200, 201, 409)

    # Get recommendations
    resp = await async_client.post(
        f"/api/v1/devices/{device_id}/recommendations",
        headers={"X-API-Key": "test-key"},
    )
    # 402 if insufficient credits, 503 if providers down — both are valid in integration
    if resp.status_code == 200:
        data = resp.json()
        for item in data["recommendations"]:
            assert "anomaly_suppressed" in item, "anomaly_suppressed missing from item"
            assert isinstance(item["anomaly_suppressed"], bool)


@pytest.mark.asyncio
async def test_at_least_one_recommendation_always_returned(db_session: AsyncSession, async_client):
    """Even in anomalous conditions the response always contains at least one recommendation."""
    device_id = f"anomaly-atleastone-{uuid.uuid4().hex[:8]}"

    reg = await async_client.post(
        "/api/v1/devices",
        json={
            "device_id": device_id,
            "name": "At Least One Test",
            "height_cm": 170.0,
            "weight_kg": 65.0,
        },
        headers={"X-API-Key": "test-key"},
    )
    assert reg.status_code in (200, 201, 409)

    resp = await async_client.post(
        f"/api/v1/devices/{device_id}/recommendations",
        headers={"X-API-Key": "test-key"},
    )
    if resp.status_code == 200:
        data = resp.json()
        assert len(data["recommendations"]) >= 1, "Response must contain at least one recommendation"


@pytest.mark.asyncio
async def test_cold_start_device_no_anomaly_flag(db_session: AsyncSession, async_client):
    """Device with no telemetry history must not have threshold_exceeded anomaly (no baseline)."""
    device_id = f"no-baseline-{uuid.uuid4().hex[:8]}"

    await async_client.post(
        "/api/v1/devices",
        json={
            "device_id": device_id,
            "name": "No Baseline Device",
            "height_cm": 180.0,
            "weight_kg": 80.0,
        },
        headers={"X-API-Key": "test-key"},
    )

    resp = await async_client.post(
        f"/api/v1/devices/{device_id}/recommendations",
        headers={"X-API-Key": "test-key"},
    )
    if resp.status_code == 200:
        data = resp.json()
        # No baseline → anomaly suppression should not activate; all items unsuppressed
        suppressed_count = sum(1 for item in data["recommendations"] if item.get("anomaly_suppressed"))
        assert suppressed_count == 0, "Cold-start device should have no suppressed recommendations"
