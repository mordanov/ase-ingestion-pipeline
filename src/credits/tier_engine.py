from src.db.models import RewardTier


class TierEngine:
    """Computes reward tier from cumulative credits spent (legacy) or earned (new)."""

    THRESHOLDS = [
        (20_000, RewardTier.platinum),
        (5_000, RewardTier.gold),
        (1_000, RewardTier.silver),
        (0, RewardTier.bronze),
    ]

    def compute_tier(self, cumulative_spent: int) -> RewardTier:
        for threshold, tier in self.THRESHOLDS:
            if cumulative_spent >= threshold:
                return tier
        return RewardTier.bronze

    def compute_tier_from_config(self, cumulative_earned: int, config) -> RewardTier:
        """Compute tier from cumulative_credits_earned using config thresholds."""
        thresholds = config.tier_thresholds  # {"silver": 1000, "gold": 5000, "platinum": 20000}
        if cumulative_earned >= thresholds.get("platinum", 20_000):
            return RewardTier.platinum
        if cumulative_earned >= thresholds.get("gold", 5_000):
            return RewardTier.gold
        if cumulative_earned >= thresholds.get("silver", 1_000):
            return RewardTier.silver
        return RewardTier.bronze

    def get_multiplier(self, tier: RewardTier, config) -> float:
        """Return the earning multiplier for a given tier from config."""
        multipliers = config.tier_multipliers  # {"bronze": 1.0, "silver": 1.25, ...}
        return float(multipliers.get(tier.value, 1.0))
