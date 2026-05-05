"""Integration tests for credit earning via activity ingestion (T021)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from src.db.models import Device
from src.db.models.credits import CreditActionType, CreditTransaction

from tests.conftest import make_telemetry_event


@pytest.mark.asyncio
async def test_ingest_workout_event_increases_balance(
    async_client: AsyncClient, seeded_device, db_session
):
    original_balance = seeded_device.credit_balance

    event = make_telemetry_event(
        device_id=seeded_device.device_id,
        scenario="workout",
    )
    resp = await async_client.post("/ingest", json=event)
    assert resp.status_code == 202
    assert resp.json()["accepted"] == 1

    await db_session.refresh(seeded_device)
    assert seeded_device.credit_balance > original_balance


@pytest.mark.asyncio
async def test_ingest_sleep_event_increases_balance_less_than_workout(
    async_client: AsyncClient, db_session
):
    device_id = f"activity-test-{uuid.uuid4().hex[:8]}"
    device = Device(
        id=uuid.uuid4(),
        device_id=device_id,
        device_type="smartwatch",
        model="Test",
        firmware_version="1.0",
        os="RTOS",
        user_id="test-user",
        height_cm=170.0,
        weight_kg=65.0,
        credit_balance=100,
        cumulative_credits_spent=0,
        reward_tier="bronze",
    )
    db_session.add(device)
    await db_session.commit()

    sleep_event = make_telemetry_event(device_id=device_id, scenario="sleep")
    resp = await async_client.post("/ingest", json=sleep_event)
    assert resp.status_code == 202

    await db_session.refresh(device)
    sleep_gain = device.credit_balance - 100

    # Reset and test workout
    device.credit_balance = 100
    await db_session.commit()

    workout_event = make_telemetry_event(device_id=device_id, scenario="workout")
    resp2 = await async_client.post("/ingest", json=workout_event)
    assert resp2.status_code == 202

    await db_session.refresh(device)
    workout_gain = device.credit_balance - 100

    assert workout_gain > sleep_gain


@pytest.mark.asyncio
async def test_duplicate_event_id_balance_unchanged(
    async_client: AsyncClient, seeded_device, db_session
):
    event = make_telemetry_event(
        device_id=seeded_device.device_id,
        scenario="workout",
    )

    resp1 = await async_client.post("/ingest", json=event)
    assert resp1.status_code == 202

    await db_session.refresh(seeded_device)
    balance_after_first = seeded_device.credit_balance

    resp2 = await async_client.post("/ingest", json=event)
    assert resp2.status_code == 202

    await db_session.refresh(seeded_device)
    assert seeded_device.credit_balance == balance_after_first


@pytest.mark.asyncio
async def test_activity_reward_transaction_recorded(
    async_client: AsyncClient, seeded_device, db_session
):
    event = make_telemetry_event(
        device_id=seeded_device.device_id,
        scenario="workout",
    )
    resp = await async_client.post("/ingest", json=event)
    assert resp.status_code == 202

    result = await db_session.execute(
        select(CreditTransaction)
        .where(CreditTransaction.device_id == seeded_device.device_id)
        .where(CreditTransaction.action_type == CreditActionType.activity_reward)
        .order_by(CreditTransaction.created_at.desc())
        .limit(1)
    )
    tx = result.scalar_one_or_none()
    assert tx is not None
    assert "workout" in tx.reason.lower()
    assert tx.amount > 0
