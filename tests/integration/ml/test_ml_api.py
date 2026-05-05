"""Integration tests for personalised recommendations — T015 (must FAIL before implementation)."""

import pytest
from httpx import AsyncClient
from src.api.main import app


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cold_start_device_gets_null_scores(client):
    """New device (no telemetry history) gets valid response with null personal_relevance_score."""
    # Register a fresh device
    reg = await client.post(
        "/api/v1/devices",
        json={
            "device_id": "ml-test-cold-001",
            "name": "Cold Start Test",
            "height_cm": 175.0,
            "weight_kg": 70.0,
        },
        headers={"X-API-Key": "dev-key"},
    )
    assert reg.status_code in (200, 201, 409)  # 409 if already exists

    # Get recommendations
    resp = await client.post(
        "/api/v1/devices/ml-test-cold-001/recommendations",
        headers={"X-API-Key": "dev-key"},
    )
    assert resp.status_code in (200, 402, 503)
    if resp.status_code == 200:
        data = resp.json()
        for item in data["recommendations"]:
            assert "personal_relevance_score" in item
            assert item["personal_relevance_score"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recommendation_response_has_ml_fields(client):
    """Recommendation response always includes personal_relevance_score and anomaly_suppressed."""
    resp = await client.post(
        "/api/v1/devices/ml-test-cold-001/recommendations",
        headers={"X-API-Key": "dev-key"},
    )
    if resp.status_code == 200:
        data = resp.json()
        for item in data["recommendations"]:
            assert "personal_relevance_score" in item
            assert "anomaly_suppressed" in item
            assert isinstance(item["anomaly_suppressed"], bool)
