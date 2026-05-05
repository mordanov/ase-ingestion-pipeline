"""Contract tests for Service2 recommendation provider.

These hit the live endpoint and verify the response schema.
Requires SERVICE2_ENDPOINT env var (or default).
"""
import json
import os
import uuid

import httpx
import pytest

SERVICE2_URL = os.getenv(
    "SERVICE2_ENDPOINT",
    "https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service2",
)

DEFAULT_BIRTH_DATE = 631152000


def _build_request(weight_kg: float = 70.0, height_cm: float = 175.0) -> dict:
    mass_lbs = round(weight_kg * 2.20462, 2)
    height_feet = round(height_cm / 30.48, 4)
    return {
        "measurements": {"mass": mass_lbs, "height": height_feet},
        "birth_date": DEFAULT_BIRTH_DATE,
        "session_token": str(uuid.uuid4()),
    }


def _unwrap(resp: httpx.Response) -> object:
    """Unwrap Lambda proxy envelope {body: str, statusCode: int} if present."""
    data = resp.json()
    if isinstance(data, dict) and "body" in data and "statusCode" in data:
        raw = data["body"]
        return json.loads(raw) if isinstance(raw, str) else raw
    return data


@pytest.mark.contract
async def test_service2_valid_request():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(SERVICE2_URL, json=_build_request())
    assert resp.status_code == 200
    data = _unwrap(resp)
    assert isinstance(data, list), "Service2 must return a list of recommendations"
    assert len(data) > 0
    for item in data:
        assert "priority" in item
        assert "title" in item
        assert 1 <= item["priority"] <= 1000, "priority must be in [1, 1000]"
        assert item["title"], "title must be non-empty"


@pytest.mark.contract
async def test_service2_session_token_uniqueness():
    """Each call uses a different session_token — both should succeed."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r1 = await client.post(SERVICE2_URL, json=_build_request())
        r2 = await client.post(SERVICE2_URL, json=_build_request())
    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.contract
async def test_service2_error_response_shape():
    """Send malformed request; verify error shape matches contract."""
    bad_payload = {"measurements": {}, "birth_date": -1, "session_token": ""}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(SERVICE2_URL, json=bad_payload)
    if resp.status_code != 200:
        assert resp.status_code in (400, 422, 500)
    else:
        data = _unwrap(resp)
        if isinstance(data, dict) and "code" in data:
            assert "error" in data
