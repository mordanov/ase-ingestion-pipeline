"""Unit tests for src/credits/ledger.py (T046)."""

from src.credits.ledger import CreditLedger


def test_validate_sufficient_returns_true():
    ledger = CreditLedger()
    assert ledger.validate_sufficient(100, cost=1) is True
    assert ledger.validate_sufficient(1, cost=1) is True


def test_validate_sufficient_returns_false_on_zero():
    ledger = CreditLedger()
    assert ledger.validate_sufficient(0, cost=1) is False
    assert ledger.validate_sufficient(-5, cost=1) is False


def test_validate_sufficient_higher_cost():
    ledger = CreditLedger()
    assert ledger.validate_sufficient(5, cost=10) is False
    assert ledger.validate_sufficient(10, cost=10) is True
