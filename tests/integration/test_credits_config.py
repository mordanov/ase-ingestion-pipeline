"""Integration tests for credit configuration CRUD (T011, T012)."""
import pytest
from httpx import AsyncClient


VALID_CONFIG = {
    "default_initial_balance": 150,
    "activity_earning_rules": {
        "workout": 10,
        "sport": 7,
        "sleep": 3,
        "rest": 1,
        "default": 2,
    },
    "service_costs": {"service1": 5, "service2": 3, "default": 4},
    "streak_bonus_7d": 25,
    "streak_bonus_30d": 100,
    "tier_thresholds": {"silver": 1000, "gold": 5000, "platinum": 20000},
    "tier_multipliers": {"bronze": 1.0, "silver": 1.25, "gold": 1.5, "platinum": 2.0},
    "tier_discounts": {"bronze": 0.0, "silver": 0.05, "gold": 0.1, "platinum": 0.2},
}


@pytest.mark.asyncio
async def test_get_credit_config_returns_200(async_client: AsyncClient):
    resp = await async_client.get(
        "/api/v1/credit-config",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "default_initial_balance" in data
    assert "activity_earning_rules" in data
    assert "service_costs" in data
    assert "tier_thresholds" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_put_credit_config_updates_and_get_reflects_change(async_client: AsyncClient):
    put_resp = await async_client.put(
        "/api/v1/credit-config",
        json=VALID_CONFIG,
        headers={"X-API-Key": "test-key"},
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["default_initial_balance"] == 150
    assert data["activity_earning_rules"]["workout"] == 10

    get_resp = await async_client.get(
        "/api/v1/credit-config",
        headers={"X-API-Key": "test-key"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["default_initial_balance"] == 150


@pytest.mark.asyncio
async def test_put_invalid_service_cost_returns_422(async_client: AsyncClient):
    invalid = dict(VALID_CONFIG)
    invalid["service_costs"] = {"default": 0}  # cost must be >= 1
    resp = await async_client.put(
        "/api/v1/credit-config",
        json=invalid,
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_non_ascending_tier_thresholds_returns_422(async_client: AsyncClient):
    invalid = dict(VALID_CONFIG)
    invalid["tier_thresholds"] = {"silver": 5000, "gold": 1000, "platinum": 20000}  # non-ascending
    resp = await async_client.put(
        "/api/v1/credit-config",
        json=invalid,
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_device_registered_after_config_change_gets_updated_initial_balance(
    async_client: AsyncClient,
):
    # Set a distinctive initial balance
    update_config = dict(VALID_CONFIG)
    update_config["default_initial_balance"] = 777
    put_resp = await async_client.put(
        "/api/v1/credit-config",
        json=update_config,
        headers={"X-API-Key": "test-key"},
    )
    assert put_resp.status_code == 200

    # Register a new device
    import uuid
    device_id = f"test-config-device-{uuid.uuid4().hex[:8]}"
    reg_resp = await async_client.post(
        "/api/v1/devices",
        json={
            "device_id": device_id,
            "device_type": "smartwatch",
            "model": "TestWatch",
            "firmware_version": "1.0.0",
            "os": "WatchOS 10",
            "user_id": "test-user",
            "height_cm": 170.0,
            "weight_kg": 65.0,
        },
        headers={"X-API-Key": "test-key"},
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["credit_balance"] == 777
