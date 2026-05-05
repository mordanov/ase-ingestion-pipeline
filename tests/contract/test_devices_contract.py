"""Contract acceptance tests for devices-api.md (T038)."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_response_has_required_fields(async_client: AsyncClient):
    payload = {
        "device_id": f"fw-test-{uuid.uuid4().hex[:8]}",
        "device_type": "fitness_tracker",
        "model": "FitBand 3",
        "firmware_version": "1.6.0",
        "os": "FitOS 2",
        "user_id": "user-contract-001",
        "height_cm": 165.0,
        "weight_kg": 60.0,
    }
    resp = await async_client.post(
        "/api/v1/devices", json=payload, headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 201
    data = resp.json()

    required = {
        "device_id",
        "device_type",
        "model",
        "firmware_version",
        "os",
        "credit_balance",
        "reward_tier",
        "registered_at",
    }
    assert required.issubset(data.keys()), f"Missing fields: {required - data.keys()}"


@pytest.mark.asyncio
async def test_register_response_no_pii(async_client: AsyncClient):
    payload = {
        "device_id": f"pii-test-{uuid.uuid4().hex[:8]}",
        "device_type": "smartwatch",
        "model": "Watch X",
        "firmware_version": "3.0.0",
        "os": "WatchOS 11",
        "user_id": "pii-user-001",
        "height_cm": 180.0,
        "weight_kg": 80.0,
    }
    resp = await async_client.post(
        "/api/v1/devices", json=payload, headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 201
    data = resp.json()

    pii_fields = {"height_cm", "weight_kg", "user_id"}
    assert not pii_fields.intersection(data.keys()), (
        f"PII leak: {pii_fields.intersection(data.keys())}"
    )


@pytest.mark.asyncio
async def test_get_unknown_device_returns_404(async_client: AsyncClient):
    resp = await async_client.get(
        "/api/v1/devices/no-such-device-xyz", headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 404
