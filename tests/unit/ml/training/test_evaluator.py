"""Unit tests for Evaluator — T033 (must FAIL before implementation)."""
import pytest

from src.ml.training.evaluator import Evaluator


@pytest.fixture
def evaluator():
    return Evaluator()


def test_ndcg_perfect_ranking(evaluator):
    y_true = [3.0, 2.0, 1.0, 0.0]
    y_score = [3.0, 2.0, 1.0, 0.0]  # perfect prediction
    score = evaluator.ndcg_at_10(y_score=y_score, y_true=y_true)
    assert score is not None
    assert abs(score - 1.0) < 0.001


def test_ndcg_returns_float_in_range(evaluator):
    y_true = [1.0, 0.0, 1.0, 0.0, 1.0]
    y_score = [0.9, 0.8, 0.3, 0.1, 0.7]
    score = evaluator.ndcg_at_10(y_score=y_score, y_true=y_true)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_ndcg_returns_none_on_empty(evaluator):
    assert evaluator.ndcg_at_10([], []) is None


def test_ndcg_returns_none_on_mismatched_length(evaluator):
    assert evaluator.ndcg_at_10([1.0, 2.0], [1.0]) is None


def test_f1_perfect_prediction(evaluator):
    y_true = [1, 0, 1, 0, 1]
    y_pred = [1, 0, 1, 0, 1]
    score = evaluator.f1_score(y_true=y_true, y_pred=y_pred)
    assert score is not None
    assert abs(score - 1.0) < 0.001


def test_f1_returns_float_in_range(evaluator):
    y_true = [1, 0, 1, 0, 1, 0]
    y_pred = [1, 1, 0, 0, 1, 0]
    score = evaluator.f1_score(y_true=y_true, y_pred=y_pred)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_f1_returns_none_on_empty(evaluator):
    assert evaluator.f1_score([], []) is None


def test_f1_returns_none_on_mismatched_length(evaluator):
    assert evaluator.f1_score([1, 0], [1]) is None


def test_f1_all_zeros_returns_zero_not_nan(evaluator):
    y_true = [0, 0, 0]
    y_pred = [0, 0, 0]
    score = evaluator.f1_score(y_true=y_true, y_pred=y_pred)
    assert score is not None
    assert score == 0.0
