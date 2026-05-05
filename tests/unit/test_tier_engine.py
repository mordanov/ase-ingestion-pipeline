"""Unit tests for src/credits/tier_engine.py (T047)."""
import pytest

from src.credits.tier_engine import TierEngine
from src.db.models import RewardTier


def test_tier_thresholds():
    engine = TierEngine()

    assert engine.compute_tier(0) == RewardTier.bronze
    assert engine.compute_tier(999) == RewardTier.bronze
    assert engine.compute_tier(1000) == RewardTier.silver
    assert engine.compute_tier(4999) == RewardTier.silver
    assert engine.compute_tier(5000) == RewardTier.gold
    assert engine.compute_tier(19999) == RewardTier.gold
    assert engine.compute_tier(20000) == RewardTier.platinum
    assert engine.compute_tier(100000) == RewardTier.platinum


def test_tier_boundary_cases():
    engine = TierEngine()
    assert engine.compute_tier(-1) == RewardTier.bronze
    assert engine.compute_tier(1001) == RewardTier.silver
