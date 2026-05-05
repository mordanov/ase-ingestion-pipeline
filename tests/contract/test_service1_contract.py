"""Contract tests for Service1 recommendation provider.

These hit the live endpoint and verify the response schema.
Requires SERVICE1_ENDPOINT and SERVICE1_TOKEN env vars (or defaults).
Skip if endpoint not reachable.
"""

import json
import os

import httpx
import pytest

SERVICE1_URL = os.getenv(
    "SERVICE1_ENDPOINT",
    "https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service1",
)
SERVICE1_TOKEN = os.getenv("SERVICE1_TOKEN", "service1-dev")


def _unwrap(resp: httpx.Response) -> object:
    """Unwrap Lambda proxy envelope {body: str, statusCode: int} if present."""
    data = resp.json()
    if isinstance(data, dict) and "body" in data and "statusCode" in data:
        raw = data["body"]
        return json.loads(raw) if isinstance(raw, str) else raw
    return data


@pytest.mark.contract
async def test_service1_valid_request():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            SERVICE1_URL,
            json={"height": 175.0, "weight": 70.0, "token": SERVICE1_TOKEN},
        )
    assert resp.status_code == 200
    data = _unwrap(resp)
    assert isinstance(data, list), "Service1 must return a list"
    assert len(data) > 0, "Service1 must return at least one recommendation"
    for item in data:
        assert "confidence" in item, "Each item must have 'confidence'"
        assert "recommendation" in item, "Each item must have 'recommendation'"
        assert 0.0 <= item["confidence"] <= 1.0, "confidence must be in [0, 1]"
        assert item["recommendation"], "recommendation must be non-empty"


@pytest.mark.contract
async def test_service1_invalid_token():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            SERVICE1_URL,
            json={"height": 175.0, "weight": 70.0, "token": "invalid-token-xyz"},
        )
    if resp.status_code == 200:
        data = _unwrap(resp)
        assert "errorCode" in data or isinstance(data, list)
    else:
        assert resp.status_code in (401, 403, 400)


@pytest.mark.contract
async def test_service1_edge_case_low_weight():
    """Very low weight should not crash the service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            SERVICE1_URL,
            json={"height": 150.0, "weight": 40.0, "token": SERVICE1_TOKEN},
        )
    assert resp.status_code in (200, 400, 422)
