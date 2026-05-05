"""Unit tests for EarningService (T020)."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models.device import Device, RewardTier
from src.db.models.credits import CreditActionType


def _make_config(
    earning_rules=None,
    tier_thresholds=None,
    tier_multipliers=None,
    streak_bonus_7d=25,
    streak_bonus_30d=100,
):
    cfg = MagicMock()
    cfg.activity_earning_rules = earning_rules or {"workout": 10, "sleep": 3, "default": 2}
    cfg.tier_thresholds = tier_thresholds or {"silver": 1000, "gold": 5000, "platinum": 20000}
    cfg.tier_multipliers = tier_multipliers or {"bronze": 1.0, "silver": 1.25, "gold": 1.5, "platinum": 2.0}
    cfg.streak_bonus_7d = streak_bonus_7d
    cfg.streak_bonus_30d = streak_bonus_30d
    return cfg


def _make_device(
    device_id="dev-001",
    credit_balance=100,
    cumulative_credits_earned=0,
    cumulative_credits_spent=0,
    reward_tier=RewardTier.bronze,
    streak_days=0,
    last_activity_date=None,
):
    d = MagicMock(spec=Device)
    d.device_id = device_id
    d.credit_balance = credit_balance
    d.cumulative_credits_earned = cumulative_credits_earned
    d.cumulative_credits_spent = cumulative_credits_spent
    d.reward_tier = reward_tier
    d.streak_days = streak_days
    d.last_activity_date = last_activity_date
    return d


def _make_event(event_id="evt-001", scenario="workout"):
    e = MagicMock()
    e.event_id = event_id
    e.scenario = scenario
    return e


@pytest.mark.asyncio
async def test_base_earning_by_scenario():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config())

    svc = EarningService(session, config_svc)
    device = _make_device()
    event = _make_event(scenario="workout")

    awarded = await svc.award_for_event(event, device)

    assert awarded == 10  # base workout earning


@pytest.mark.asyncio
async def test_sleep_earns_less_than_workout():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config())

    svc = EarningService(session, config_svc)
    device = _make_device()
    sleep_event = _make_event(scenario="sleep")

    awarded = await svc.award_for_event(sleep_event, device)

    assert awarded == 3  # base sleep earning < workout


@pytest.mark.asyncio
async def test_tier_multiplier_applied_for_silver():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config())

    svc = EarningService(session, config_svc)
    device = _make_device(reward_tier=RewardTier.silver)
    event = _make_event(scenario="workout")

    awarded = await svc.award_for_event(event, device)

    assert awarded == int(10 * 1.25)  # workout × silver multiplier


@pytest.mark.asyncio
async def test_streak_increments_on_new_day_event():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config())

    today = date.today()
    yesterday = today - timedelta(days=1)

    svc = EarningService(session, config_svc)
    device = _make_device(streak_days=3, last_activity_date=yesterday)
    event = _make_event(scenario="workout")

    await svc.award_for_event(event, device)

    assert device.streak_days == 4
    assert device.last_activity_date == today


@pytest.mark.asyncio
async def test_streak_resets_on_gap_greater_than_one_day():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config())

    today = date.today()
    three_days_ago = today - timedelta(days=3)

    svc = EarningService(session, config_svc)
    device = _make_device(streak_days=10, last_activity_date=three_days_ago)
    event = _make_event(scenario="workout")

    await svc.award_for_event(event, device)

    assert device.streak_days == 1  # reset to 1 for current day


@pytest.mark.asyncio
async def test_seven_day_streak_bonus_awarded():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config(streak_bonus_7d=25))

    today = date.today()
    yesterday = today - timedelta(days=1)

    svc = EarningService(session, config_svc)
    # At 6 days → after event will be 7
    device = _make_device(streak_days=6, last_activity_date=yesterday)
    event = _make_event(scenario="workout")

    awarded = await svc.award_for_event(event, device)

    # base (10) + streak bonus (25)
    assert awarded >= 10 + 25


@pytest.mark.asyncio
async def test_duplicate_event_id_returns_zero():
    from src.credits.earning_service import EarningService

    session = AsyncMock()
    # Simulate existing event_id in credit_transactions
    existing_row = MagicMock()
    existing_row.scalar_one_or_none = lambda: "existing-tx-id"
    session.execute = AsyncMock(return_value=existing_row)

    config_svc = AsyncMock()
    config_svc.get_active = AsyncMock(return_value=_make_config())

    svc = EarningService(session, config_svc)
    device = _make_device()
    event = _make_event()

    awarded = await svc.award_for_event(event, device)

    assert awarded == 0
