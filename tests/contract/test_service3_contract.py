"""Contract tests for Service3 external recommendation provider.

Skipped unless SERVICE3_ENDPOINT env var is set.
"""
import os
import pytest
import pytest_asyncio
import httpx

SERVICE3_ENDPOINT = os.getenv("SERVICE3_ENDPOINT", "")

pytestmark = pytest.mark.skipif(
    not SERVICE3_ENDPOINT,
    reason="SERVICE3_ENDPOINT not configured; skipping live contract test",
)


@pytest_asyncio.fixture
async def http_client():
    async with httpx.AsyncClient(base_url=SERVICE3_ENDPOINT, timeout=10.0) as client:
        yield client


@pytest.mark.asyncio
async def test_service3_returns_recommendations(http_client):
    """Service3 should return a non-empty list of recommendations for valid input."""
    schema = os.getenv("SERVICE3_SCHEMA", "service1_schema")

    if schema == "service1_schema":
        payload = {
            "height": 175.0,
            "weight": 70.0,
            "token": os.getenv("SERVICE3_API_KEY", "test-token"),
        }
        resp = await http_client.post("/recommend", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)
        assert len(body["recommendations"]) > 0
        first = body["recommendations"][0]
        assert "shortText" in first
        assert "confidence" in first
        assert isinstance(first["confidence"], (int, float))
    else:
        payload = {
            "weight": 70.0 * 2.20462,
            "height": 175.0 / 30.48,
        }
        resp = await http_client.post("/health/suggestions", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "suggestions" in body
        assert isinstance(body["suggestions"], list)
        assert len(body["suggestions"]) > 0
        first = body["suggestions"][0]
        assert "text" in first
        assert "priority" in first
        assert isinstance(first["priority"], (int, float))


@pytest.mark.asyncio
async def test_service3_handles_missing_fields(http_client):
    """Service3 should return a client error for incomplete input."""
    resp = await http_client.post("/recommend", json={})
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_service3_normalised_score_range(http_client):
    """Normalised scores from Service3 must fall in [0, 1000]."""
    from src.recommendation.adapters.service3_adapter import Service3Adapter
    from src.config import Settings

    settings = Settings(
        service3_endpoint=SERVICE3_ENDPOINT,
        service3_schema=os.getenv("SERVICE3_SCHEMA", "service1_schema"),
    )
    async with httpx.AsyncClient() as client:
        adapter = Service3Adapter(client, settings)
        result = await adapter.get_recommendations(175.0, 70.0)

    assert result.error is None, f"Unexpected error: {result.error}"
    for rec in result.recommendations:
        assert 0.0 <= rec.normalised_score <= 1000.0, (
            f"Score {rec.normalised_score} out of expected range for provider {rec.provider_id}"
        )
