import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.credit_config import CreditConfig

_DEFAULT_CONFIG = {
    "version": 1,
    "is_active": True,
    "default_initial_balance": 100,
    "activity_earning_rules": {
        "workout": 10,
        "sport": 7,
        "sleep": 3,
        "rest": 1,
        "default": 2,
    },
    "service_costs": {"service1": 100, "service2": 100, "default": 100},
    "streak_bonus_7d": 25,
    "streak_bonus_30d": 100,
    "tier_thresholds": {"silver": 1000, "gold": 5000, "platinum": 20000},
    "tier_multipliers": {"bronze": 1.0, "silver": 1.25, "gold": 1.5, "platinum": 2.0},
    "tier_discounts": {"bronze": 0.0, "silver": 0.05, "gold": 0.1, "platinum": 0.2},
    "created_by": "system",
}


class ConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> CreditConfig:
        result = await self._session.execute(
            select(CreditConfig).where(CreditConfig.is_active.is_(True))
        )
        config = result.scalar_one_or_none()
        if config is None:
            await self.seed_default_if_missing()
            result = await self._session.execute(
                select(CreditConfig).where(CreditConfig.is_active.is_(True))
            )
            config = result.scalar_one()
        return config

    async def create_new_version(self, data: dict, created_by: str = "api") -> CreditConfig:
        # Deactivate current active config
        await self._session.execute(
            update(CreditConfig).where(CreditConfig.is_active.is_(True)).values(is_active=False)
        )

        # Get next version number
        result = await self._session.execute(
            select(CreditConfig.version).order_by(CreditConfig.version.desc()).limit(1)
        )
        last_version = result.scalar_one_or_none() or 0

        config = CreditConfig(
            id=uuid.uuid4(),
            version=last_version + 1,
            is_active=True,
            created_by=created_by,
            created_at=datetime.now(UTC),
            **{
                k: v
                for k, v in data.items()
                if k not in ("version", "is_active", "created_by", "created_at", "id")
            },
        )
        self._session.add(config)
        await self._session.commit()
        await self._session.refresh(config)
        return config

    async def seed_default_if_missing(self) -> None:
        result = await self._session.execute(
            select(CreditConfig.id).where(CreditConfig.is_active.is_(True)).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return

        config = CreditConfig(
            id=uuid.uuid4(),
            **_DEFAULT_CONFIG,
        )
        self._session.add(config)
        await self._session.commit()
