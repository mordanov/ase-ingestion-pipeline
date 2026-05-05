"""Integration tests for credits and reward tier (T048)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from src.db.models import Device
from src.recommendation.interfaces import ProviderResult, RawRecommendation
from tests.conftest import make_telemetry_event


def _mock_provider_result(provider_id: str = "service1") -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id,
        recommendations=[RawRecommendation(short_text="Walk more", detail=None, normalised_score=500.0, provider_id=provider_id)],
        error=None,
        duration_ms=50,
    )


@pytest.mark.asyncio
async def test_recommendation_deducts_credit(async_client: AsyncClient, seeded_device, db_session):
    initial_balance = seeded_device.credit_balance

    with patch("src.recommendation.adapters.service1_adapter.Service1Adapter.get_recommendations",
               new_callable=AsyncMock, return_value=_mock_provider_result("service1")):
        resp = await async_client.post(
            f"/api/v1/devices/{seeded_device.device_id}/recommendations",
            headers={"X-API-Key": "test-key"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["credits_remaining"] == initial_balance - 1


@pytest.mark.asyncio
async def test_zero_balance_returns_402(async_client: AsyncClient, db_session, seeded_device):
    await db_session.execute(
        update(Device).where(Device.device_id == seeded_device.device_id).values(credit_balance=0)
    )
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/devices/{seeded_device.device_id}/recommendations",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_topup_increases_balance(async_client: AsyncClient, seeded_device, db_session):
    original_balance = seeded_device.credit_balance
    resp = await async_client.post(
        f"/api/v1/devices/{seeded_device.device_id}/credits",
        json={"amount": 50},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["credit_balance"] == original_balance + 50


@pytest.mark.asyncio
async def test_tier_upgrades_to_silver_at_1000_cumulative(async_client: AsyncClient, db_session, seeded_device):
    await db_session.execute(
        update(Device).where(Device.device_id == seeded_device.device_id)
        .values(cumulative_credits_spent=999, credit_balance=50)
    )
    await db_session.commit()

    with patch("src.recommendation.adapters.service1_adapter.Service1Adapter.get_recommendations",
               new_callable=AsyncMock, return_value=_mock_provider_result("service1")):
        resp = await async_client.post(
            f"/api/v1/devices/{seeded_device.device_id}/recommendations",
            headers={"X-API-Key": "test-key"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["reward_tier"] == "silver"
