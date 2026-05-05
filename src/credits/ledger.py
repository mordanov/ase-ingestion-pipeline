import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.credits.tier_engine import TierEngine
from src.db.models.credits import CreditActionType, CreditTransaction
from src.db.models.device import Device
from src.observability.logging import get_logger
from src.observability.metrics import (
    DEVICE_CREDIT_BALANCE,
    DEVICE_CREDITS_EARNED,
    DEVICE_CREDITS_SPENT,
)

logger = get_logger(__name__)
_tier_engine = TierEngine()


class CreditLedger:
    """Credit ledger — balance mutations and transaction persistence."""

    def validate_sufficient(self, balance: int, cost: int = 1) -> bool:
        return balance >= cost

    @staticmethod
    def _update_cumulative_totals(device: Device, delta: int) -> None:
        if delta > 0:
            device.cumulative_credits_earned = (device.cumulative_credits_earned or 0) + delta
            return
        device.cumulative_credits_spent = (device.cumulative_credits_spent or 0) + abs(delta)

    @staticmethod
    def _emit_metrics(
        device: Device, delta: int, action_type: CreditActionType, new_balance: int
    ) -> None:
        DEVICE_CREDIT_BALANCE.labels(device_id=device.device_id).set(new_balance)
        if delta > 0:
            DEVICE_CREDITS_EARNED.labels(
                device_id=device.device_id,
                action_type=action_type.value,
            ).inc(delta)
            return
        DEVICE_CREDITS_SPENT.labels(device_id=device.device_id).inc(abs(delta))

    async def update_device_balance(
        self,
        session: AsyncSession,
        device: Device,
        delta: int,
        action_type: CreditActionType,
        reason: str,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
        config=None,
    ) -> int:
        """Apply delta to device balance, persist a transaction, update tier, return new balance."""
        new_balance = device.credit_balance + delta
        device.credit_balance = new_balance

        self._update_cumulative_totals(device, delta)

        # Recompute tier from cumulative_earned if config available
        if config is not None:
            device.reward_tier = _tier_engine.compute_tier_from_config(
                device.cumulative_credits_earned or 0, config
            )
        else:
            device.reward_tier = _tier_engine.compute_tier(device.cumulative_credits_spent or 0)

        await self.record_transaction(
            session=session,
            device_id=device.device_id,
            amount=delta,
            action_type=action_type,
            reason=reason,
            resulting_balance=new_balance,
            metadata=metadata,
            event_id=event_id,
        )

        with suppress(Exception):
            self._emit_metrics(device, delta, action_type, new_balance)

        return new_balance

    async def record_transaction(
        self,
        session: AsyncSession,
        device_id: str,
        amount: int,
        action_type: CreditActionType,
        reason: str,
        resulting_balance: int,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> CreditTransaction:
        tx = CreditTransaction(
            id=uuid.uuid4(),
            device_id=device_id,
            amount=amount,
            action_type=action_type,
            reason=reason,
            resulting_balance=resulting_balance,
            metadata_=metadata,
            event_id=event_id,
            created_at=datetime.now(UTC),
        )
        session.add(tx)
        return tx
