from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.credits.ledger import CreditLedger
from src.credits.tier_engine import TierEngine
from src.db.models.credits import CreditActionType, CreditTransaction
from src.db.models.device import Device
from src.observability.logging import get_logger

logger = get_logger(__name__)
_tier_engine = TierEngine()
_ledger = CreditLedger()


class EarningService:
    def __init__(self, session: AsyncSession, config_service) -> None:
        self._session = session
        self._config_service = config_service

    async def award_for_event(self, event, device: Device) -> int:
        """Award credits for an ingestion event. Returns total credits awarded (0 if duplicate)."""
        config = await self._config_service.get_active()

        # Deduplication: check if this event_id already has an activity_reward transaction
        dup_result = await self._session.execute(
            select(CreditTransaction.id).where(
                CreditTransaction.event_id == event.event_id,
                CreditTransaction.action_type == CreditActionType.activity_reward,
            )
        )
        if dup_result.scalar_one_or_none() is not None:
            return 0

        # Base earning from scenario (scenario lives in event.payload, not as a direct attribute)
        scenario = getattr(event, "scenario", None) or event.payload.get("scenario", "default")
        rules = config.activity_earning_rules
        base_amount = rules.get(scenario, rules.get("default", 0))
        if base_amount <= 0:
            return 0

        # Apply tier multiplier
        multiplier = _tier_engine.get_multiplier(device.reward_tier, config)
        earned = int(base_amount * multiplier)

        # Write balance change + transaction
        await _ledger.update_device_balance(
            session=self._session,
            device=device,
            delta=earned,
            action_type=CreditActionType.activity_reward,
            reason=f"{scenario} activity reward",
            metadata={"scenario": scenario, "base_amount": base_amount, "multiplier": multiplier},
            event_id=event.event_id,
            config=config,
        )

        # Update streak
        today = date.today()
        last = device.last_activity_date
        total_bonus = 0

        if last is None or last < today:
            if last is not None and last == today - timedelta(days=1):
                device.streak_days = (device.streak_days or 0) + 1
            elif last is None or last < today - timedelta(days=1):
                device.streak_days = 1
            device.last_activity_date = today

            from src.observability.metrics import DEVICE_STREAK_DAYS

            DEVICE_STREAK_DAYS.labels(device_id=device.device_id).set(device.streak_days or 0)

            # Check streak milestones
            new_streak = device.streak_days
            if new_streak % 30 == 0:
                bonus = config.streak_bonus_30d
                await _ledger.update_device_balance(
                    session=self._session,
                    device=device,
                    delta=bonus,
                    action_type=CreditActionType.streak_bonus,
                    reason=f"{new_streak}-day streak bonus",
                    metadata={"streak_days": new_streak},
                    config=config,
                )
                total_bonus += bonus
            elif new_streak % 7 == 0:
                bonus = config.streak_bonus_7d
                await _ledger.update_device_balance(
                    session=self._session,
                    device=device,
                    delta=bonus,
                    action_type=CreditActionType.streak_bonus,
                    reason=f"{new_streak}-day streak bonus",
                    metadata={"streak_days": new_streak},
                    config=config,
                )
                total_bonus += bonus

        total_awarded = earned + total_bonus
        logger.info(
            "credits_awarded",
            device_id=device.device_id,
            event_id=event.event_id,
            scenario=scenario,
            earned=earned,
            streak_bonus=total_bonus,
            total=total_awarded,
        )
        return total_awarded
