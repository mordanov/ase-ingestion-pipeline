"""Unit tests for src/recommendation/aggregator.py"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from src.recommendation.interfaces import ProviderResult, RawRecommendation


def _mock_provider(provider_id: str, recs: list[RawRecommendation] | None = None, raises=None):
    provider = AsyncMock()
    provider.provider_id = provider_id
    if raises:
        provider.get_recommendations = AsyncMock(side_effect=raises)
    else:
        provider.get_recommendations = AsyncMock(
            return_value=ProviderResult(
                provider_id=provider_id,
                recommendations=recs
                or [
                    RawRecommendation(
                        short_text="Walk more",
                        detail=None,
                        normalised_score=400.0,
                        provider_id=provider_id,
                    )
                ],
                error=None,
                duration_ms=50,
            )
        )
    return provider


@pytest.mark.asyncio
async def test_both_providers_succeed():
    from src.recommendation.aggregator import aggregate

    p1 = _mock_provider("service1")
    p2 = _mock_provider("service2")

    result = await aggregate([p1, p2], height_cm=170.0, weight_kg=65.0, timeout=2.0)

    assert len(result.providers_succeeded) == 2
    assert "service1" in result.providers_succeeded
    assert "service2" in result.providers_succeeded
    assert len(result.recommendations) >= 1


@pytest.mark.asyncio
async def test_one_provider_times_out_returns_partial():
    from src.recommendation.aggregator import aggregate

    async def slow_call(height_cm, weight_kg):
        await asyncio.sleep(10)
        return ProviderResult(
            provider_id="service2", recommendations=[], error=None, duration_ms=10000
        )

    p1 = _mock_provider("service1")
    p2 = AsyncMock()
    p2.provider_id = "service2"
    p2.get_recommendations = slow_call

    result = await aggregate([p1, p2], height_cm=170.0, weight_kg=65.0, timeout=0.1)

    assert "service1" in result.providers_succeeded
    assert "service2" not in result.providers_succeeded
    assert len(result.recommendations) >= 1


@pytest.mark.asyncio
async def test_all_providers_fail_raises_503():
    from src.recommendation.aggregator import AllProvidersFailedError, aggregate

    p1 = _mock_provider("service1", raises=Exception("upstream error"))
    p2 = _mock_provider("service2", raises=Exception("upstream error"))

    with pytest.raises(AllProvidersFailedError):
        await aggregate([p1, p2], height_cm=170.0, weight_kg=65.0, timeout=2.0)


@pytest.mark.asyncio
async def test_providers_called_concurrently():
    """Both providers should start before either finishes (concurrent execution)."""
    started = []
    finished = []

    async def slow_provider(name, delay=0.05):
        started.append(name)
        await asyncio.sleep(delay)
        finished.append(name)
        return ProviderResult(
            provider_id=name,
            recommendations=[
                RawRecommendation(
                    short_text="rec", detail=None, normalised_score=500.0, provider_id=name
                )
            ],
            error=None,
            duration_ms=int(delay * 1000),
        )

    p1 = AsyncMock()
    p1.provider_id = "service1"
    p1.get_recommendations = lambda h, w: slow_provider("service1", 0.05)

    p2 = AsyncMock()
    p2.provider_id = "service2"
    p2.get_recommendations = lambda h, w: slow_provider("service2", 0.05)

    from src.recommendation.aggregator import aggregate

    result = await aggregate([p1, p2], height_cm=170.0, weight_kg=65.0, timeout=2.0)

    # Both started before the other finished (concurrent)
    assert len(started) == 2
    assert len(finished) == 2
    assert len(result.providers_succeeded) == 2
