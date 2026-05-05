"""Unit tests for TierEngine tier transitions (T040)."""
from unittest.mock import MagicMock

import pytest

from src.db.models.device import RewardTier
from src.credits.tier_engine import TierEngine


def _make_config(thresholds=None, multipliers=None):
    cfg = MagicMock()
    cfg.tier_thresholds = thresholds or {"silver": 1000, "gold": 5000, "platinum": 20000}
    cfg.tier_multipliers = multipliers or {"bronze": 1.0, "silver": 1.25, "gold": 1.5, "platinum": 2.0}
    return cfg


def test_bronze_to_silver_at_threshold():
    engine = TierEngine()
    config = _make_config()
    assert engine.compute_tier_from_config(999, config) == RewardTier.bronze
    assert engine.compute_tier_from_config(1000, config) == RewardTier.silver


def test_silver_to_gold_at_threshold():
    engine = TierEngine()
    config = _make_config()
    assert engine.compute_tier_from_config(4999, config) == RewardTier.silver
    assert engine.compute_tier_from_config(5000, config) == RewardTier.gold


def test_gold_to_platinum_at_threshold():
    engine = TierEngine()
    config = _make_config()
    assert engine.compute_tier_from_config(19999, config) == RewardTier.gold
    assert engine.compute_tier_from_config(20000, config) == RewardTier.platinum


def test_multiplier_lookup_per_tier():
    engine = TierEngine()
    config = _make_config()
    assert engine.get_multiplier(RewardTier.bronze, config) == 1.0
    assert engine.get_multiplier(RewardTier.silver, config) == 1.25
    assert engine.get_multiplier(RewardTier.gold, config) == 1.5
    assert engine.get_multiplier(RewardTier.platinum, config) == 2.0


def test_custom_thresholds_loaded_from_config():
    engine = TierEngine()
    config = _make_config(thresholds={"silver": 500, "gold": 2000, "platinum": 10000})
    assert engine.compute_tier_from_config(499, config) == RewardTier.bronze
    assert engine.compute_tier_from_config(500, config) == RewardTier.silver
    assert engine.compute_tier_from_config(2000, config) == RewardTier.gold


def test_tier_at_zero_is_bronze():
    engine = TierEngine()
    config = _make_config()
    assert engine.compute_tier_from_config(0, config) == RewardTier.bronze


def test_very_high_earned_stays_platinum():
    engine = TierEngine()
    config = _make_config()
    assert engine.compute_tier_from_config(1_000_000, config) == RewardTier.platinum
