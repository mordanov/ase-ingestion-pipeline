"""Integration tests for device registration (T037)."""

import uuid

import pytest
from httpx import AsyncClient


def _registration_payload(device_id: str | None = None) -> dict:
    return {
        "device_id": device_id or f"smartwatch-reg-{uuid.uuid4().hex[:8]}",
        "device_type": "smartwatch",
        "model": "TestWatch Pro",
        "firmware_version": "2.2.3",
        "os": "WatchOS 10",
        "user_id": "user-reg-001",
        "height_cm": 172.0,
        "weight_kg": 68.5,
    }


@pytest.mark.asyncio
async def test_register_device_returns_201(async_client: AsyncClient):
    payload = _registration_payload()
    resp = await async_client.post(
        "/api/v1/devices", json=payload, headers={"X-API-Key": "test-key"}
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["device_id"] == payload["device_id"]
    assert data["credit_balance"] == 100
    assert data["reward_tier"] == "bronze"
    assert "height_cm" not in data, "PII field must not appear in response"
    assert "weight_kg" not in data, "PII field must not appear in response"
    assert "user_id" not in data, "PII field must not appear in response"


@pytest.mark.asyncio
async def test_register_device_idempotent(async_client: AsyncClient):
    payload = _registration_payload()
    r1 = await async_client.post("/api/v1/devices", json=payload, headers={"X-API-Key": "test-key"})
    r2 = await async_client.post("/api/v1/devices", json=payload, headers={"X-API-Key": "test-key"})

    # Second call is idempotent — returns 201 or 200 but not error
    assert r1.status_code == 201
    assert r2.status_code in (200, 201)
    assert r1.json()["device_id"] == r2.json()["device_id"]


@pytest.mark.asyncio
async def test_get_device_returns_twin_state(async_client: AsyncClient):
    payload = _registration_payload()
    r1 = await async_client.post("/api/v1/devices", json=payload, headers={"X-API-Key": "test-key"})
    assert r1.status_code == 201

    device_id = r1.json()["device_id"]
    r2 = await async_client.get(f"/api/v1/devices/{device_id}", headers={"X-API-Key": "test-key"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["device_id"] == device_id


@pytest.mark.asyncio
async def test_get_unknown_device_returns_404(async_client: AsyncClient):
    resp = await async_client.get(
        "/api/v1/devices/nonexistent-xyz", headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 404
