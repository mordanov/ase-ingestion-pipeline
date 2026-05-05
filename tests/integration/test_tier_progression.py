"""Integration tests for automatic tier upgrade via activity earning (T041)."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from src.db.models import Device
from src.db.models.device import DeviceType, RewardTier
from tests.conftest import make_telemetry_event


@pytest.mark.asyncio
async def test_tier_upgrades_to_silver_on_earning_cross_threshold(
    async_client: AsyncClient, db_session
):
    # Seed a device just below silver threshold (1000 earned)
    device_id = f"tier-test-{uuid.uuid4().hex[:8]}"
    device = Device(
        id=uuid.uuid4(),
        device_id=device_id,
        device_type=DeviceType.smartwatch,
        model="TierWatch",
        firmware_version="1.0.0",
        os="RTOS",
        user_id="tier-user",
        height_cm=175.0,
        weight_kg=70.0,
        credit_balance=200,
        cumulative_credits_spent=0,
        cumulative_credits_earned=995,  # 5 below silver threshold
        reward_tier=RewardTier.bronze,
        registered_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(device)
    await db_session.commit()

    # Ingest a workout event — earns >=5 credits (base 10 × 1.0 = 10)
    event = make_telemetry_event(device_id=device_id, scenario="workout")
    resp = await async_client.post("/ingest", json=event)
    assert resp.status_code == 202
    assert resp.json()["accepted"] == 1

    await db_session.refresh(device)
    # cumulative_earned should now be >=1000 → tier should be silver
    assert device.cumulative_credits_earned >= 1000
    assert device.reward_tier == RewardTier.silver
