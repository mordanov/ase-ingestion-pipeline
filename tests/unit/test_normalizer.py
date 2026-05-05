"""Unit tests for src/recommendation/normalizer.py"""
import pytest

from src.recommendation.interfaces import RawRecommendation


def _raw(short_text: str, score: float, provider: str, detail: str | None = None) -> RawRecommendation:
    return RawRecommendation(
        short_text=short_text,
        detail=detail,
        normalised_score=score,
        provider_id=provider,
    )


def test_service1_confidence_normalisation():
    from src.recommendation.normalizer import normalize_score

    assert normalize_score("service1", confidence=0.4) == pytest.approx(400.0)
    assert normalize_score("service1", confidence=1.0) == pytest.approx(1000.0)
    assert normalize_score("service1", confidence=0.0) == pytest.approx(0.0)


def test_service2_priority_passthrough():
    from src.recommendation.normalizer import normalize_score

    assert normalize_score("service2", priority=750) == pytest.approx(750.0)
    assert normalize_score("service2", priority=1) == pytest.approx(1.0)
    assert normalize_score("service2", priority=1000) == pytest.approx(1000.0)


def test_group_and_sort_merges_same_text():
    from src.recommendation.normalizer import group_and_sort

    recs = [
        _raw("Walk more", 400.0, "service1"),
        _raw("Walk more", 350.0, "service2"),
        _raw("Have more workouts per day", 750.0, "service2"),
    ]
    result = group_and_sort(recs, min_score=0.0)

    assert len(result) == 2
    # highest score first
    assert result[0].short_text == "have more workouts per day"
    assert result[0].max_score == pytest.approx(750.0)
    assert result[1].short_text == "walk more"
    assert result[1].max_score == pytest.approx(400.0)
    assert set(result[1].providers) == {"service1", "service2"}


def test_group_and_sort_case_insensitive():
    from src.recommendation.normalizer import group_and_sort

    recs = [
        _raw("Walk More", 400.0, "service1"),
        _raw("walk more", 350.0, "service2"),
    ]
    result = group_and_sort(recs, min_score=0.0)
    assert len(result) == 1
    assert result[0].max_score == pytest.approx(400.0)


def test_group_and_sort_filters_below_min_score():
    from src.recommendation.normalizer import group_and_sort

    recs = [
        _raw("Walk more", 150.0, "service1"),
        _raw("Exercise daily", 500.0, "service2"),
    ]
    result = group_and_sort(recs, min_score=200.0)
    assert len(result) == 1
    assert result[0].short_text == "exercise daily"


def test_group_and_sort_empty_input():
    from src.recommendation.normalizer import group_and_sort

    assert group_and_sort([], min_score=0.0) == []


def test_group_and_sort_detail_from_highest_score():
    from src.recommendation.normalizer import group_and_sort

    recs = [
        _raw("Walk more", 300.0, "service1", detail="Detail from s1"),
        _raw("Walk more", 500.0, "service2", detail="Detail from s2"),
    ]
    result = group_and_sort(recs, min_score=0.0)
    assert result[0].detail == "Detail from s2"
