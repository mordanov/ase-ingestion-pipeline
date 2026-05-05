"""Credits domain models — enums are defined in db/models to avoid duplication."""

from src.db.models import CreditActionType, RewardTier

TIER_THRESHOLDS = {
    RewardTier.platinum: 20_000,
    RewardTier.gold: 5_000,
    RewardTier.silver: 1_000,
    RewardTier.bronze: 0,
}

__all__ = ["RewardTier", "CreditActionType", "TIER_THRESHOLDS"]
