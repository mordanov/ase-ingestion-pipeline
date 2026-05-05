"""Integration tests for device credit detail endpoints (T028)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from src.db.models.credits import CreditActionType, CreditTransaction


@pytest.mark.asyncio
async def test_get_device_credits_returns_expected_fields(async_client: AsyncClient, seeded_device):
    resp = await async_client.get(
        f"/api/v1/devices/{seeded_device.device_id}/credits",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "credit_balance" in data
    assert "reward_tier" in data
    assert "streak_days" in data
    assert "cumulative_credits_earned" in data
    assert "cumulative_credits_spent" in data
    assert "next_tier" in data
    assert "credits_to_next_tier" in data
    assert "tier_multiplier" in data
    assert "tier_discount" in data


@pytest.mark.asyncio
async def test_get_device_credits_unknown_device_returns_404(async_client: AsyncClient):
    resp = await async_client.get(
        "/api/v1/devices/nonexistent-device-xyz/credits",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_device_transactions_returns_paginated_list(
    async_client: AsyncClient, seeded_device, db_session
):
    resp = await async_client.get(
        f"/api/v1/devices/{seeded_device.device_id}/credits/transactions",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_device_transactions_pagination_params(async_client: AsyncClient, seeded_device):
    resp = await async_client.get(
        f"/api/v1/devices/{seeded_device.device_id}/credits/transactions?limit=10&offset=0",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 10


@pytest.mark.asyncio
async def test_topup_with_reason_stores_reason_in_transaction(
    async_client: AsyncClient, seeded_device, db_session
):
    custom_reason = "promotional bonus Q1 2026"
    resp = await async_client.post(
        f"/api/v1/devices/{seeded_device.device_id}/credits",
        json={"amount": 25, "reason": custom_reason},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(CreditTransaction)
        .where(CreditTransaction.device_id == seeded_device.device_id)
        .where(CreditTransaction.action_type == CreditActionType.top_up)
        .order_by(CreditTransaction.created_at.desc())
        .limit(1)
    )
    tx = result.scalar_one_or_none()
    assert tx is not None
    assert tx.reason == custom_reason
