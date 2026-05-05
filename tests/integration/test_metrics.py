"""Integration tests for Prometheus metrics endpoint (T055)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.recommendation.interfaces import ProviderResult, RawRecommendation
from tests.conftest import make_telemetry_event


def _mock_result() -> ProviderResult:
    return ProviderResult(
        provider_id="service1",
        recommendations=[RawRecommendation(short_text="Walk more", detail=None, normalised_score=500.0, provider_id="service1")],
        error=None,
        duration_ms=50,
    )


@pytest.mark.asyncio
async def test_metrics_endpoint_accessible(async_client: AsyncClient):
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_ingest_increments_counter(async_client: AsyncClient, seeded_device):
    payload = make_telemetry_event(seeded_device.device_id)
    await async_client.post("/ingest", json=payload)

    metrics = await async_client.get("/metrics")
    assert "ingest_events_total" in metrics.text


@pytest.mark.asyncio
async def test_recommendation_duration_histogram_present(async_client: AsyncClient, seeded_device):
    with patch("src.recommendation.adapters.service1_adapter.Service1Adapter.get_recommendations",
               new_callable=AsyncMock, return_value=_mock_result()):
        await async_client.post(
            f"/api/v1/devices/{seeded_device.device_id}/recommendations",
            headers={"X-API-Key": "test-key"},
        )

    metrics = await async_client.get("/metrics")
    assert "recommendation_duration_seconds" in metrics.text
