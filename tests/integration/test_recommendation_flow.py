"""Integration tests for POST /api/v1/devices/{id}/recommendations (T018)."""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from src.recommendation.interfaces import ProviderResult, RawRecommendation


def _mock_provider_result(provider_id: str, score: float = 500.0) -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id,
        recommendations=[
            RawRecommendation(short_text="Walk more", detail="Detail", normalised_score=score, provider_id=provider_id)
        ],
        error=None,
        duration_ms=50,
    )


@pytest.mark.asyncio
async def test_recommendations_returns_200_with_results(async_client: AsyncClient, seeded_device):
    with (
        patch("src.recommendation.adapters.service1_adapter.Service1Adapter.get_recommendations",
              new_callable=AsyncMock, return_value=_mock_provider_result("service1")) as _,
        patch("src.recommendation.adapters.service2_adapter.Service2Adapter.get_recommendations",
              new_callable=AsyncMock, return_value=_mock_provider_result("service2")) as _,
    ):
        resp = await async_client.post(
            f"/api/v1/devices/{seeded_device.device_id}/recommendations",
            headers={"X-API-Key": "test-key"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) >= 1
    assert data["duration_ms"] < 1000


@pytest.mark.asyncio
async def test_recommendations_sorted_by_score_desc(async_client: AsyncClient, seeded_device):
    with (
        patch("src.recommendation.adapters.service1_adapter.Service1Adapter.get_recommendations",
              new_callable=AsyncMock, return_value=ProviderResult(
                  provider_id="service1",
                  recommendations=[
                      RawRecommendation(short_text="Walk more", detail=None, normalised_score=400.0, provider_id="service1"),
                      RawRecommendation(short_text="Sleep better", detail=None, normalised_score=700.0, provider_id="service1"),
                  ],
                  error=None,
                  duration_ms=40,
              )),
        patch("src.recommendation.adapters.service2_adapter.Service2Adapter.get_recommendations",
              new_callable=AsyncMock, return_value=ProviderResult(
                  provider_id="service2", recommendations=[], error=None, duration_ms=30,
              )),
    ):
        resp = await async_client.post(
            f"/api/v1/devices/{seeded_device.device_id}/recommendations",
            headers={"X-API-Key": "test-key"},
        )

    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    scores = [r["max_score"] for r in recs]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_recommendations_returns_402_on_zero_credits(async_client: AsyncClient, db_session, seeded_device):
    seeded_device.credit_balance = 0
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/devices/{seeded_device.device_id}/recommendations",
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 402
    assert "credits" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_recommendations_providers_succeeded_in_response(async_client: AsyncClient, seeded_device):
    with (
        patch("src.recommendation.adapters.service1_adapter.Service1Adapter.get_recommendations",
              new_callable=AsyncMock, return_value=_mock_provider_result("service1", 600.0)),
        patch("src.recommendation.adapters.service2_adapter.Service2Adapter.get_recommendations",
              new_callable=AsyncMock, return_value=_mock_provider_result("service2", 400.0)),
    ):
        resp = await async_client.post(
            f"/api/v1/devices/{seeded_device.device_id}/recommendations",
            headers={"X-API-Key": "test-key"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "providers_succeeded" in data
    assert len(data["providers_succeeded"]) >= 1
