"""Unit tests for post_with_retry and adapter retry integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.recommendation.retry import post_with_retry


def _mock_response(status_code: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = []
    return resp


# ---------------------------------------------------------------------------
# post_with_retry — core behaviour (US1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    client = MagicMock()
    client.post = AsyncMock(return_value=_mock_response(200))

    result = await post_with_retry(client, "http://example.com", {}, "svc1")

    assert result is not None
    assert result.status_code == 200
    client.post.assert_called_once()


@pytest.mark.asyncio
async def test_retry_on_5xx_then_success():
    client = MagicMock()
    client.post = AsyncMock(
        side_effect=[_mock_response(503), _mock_response(503), _mock_response(200)]
    )

    result = await post_with_retry(client, "http://example.com", {}, "svc1")

    assert result is not None
    assert result.status_code == 200
    assert client.post.call_count == 3


@pytest.mark.asyncio
async def test_no_retry_on_4xx():
    client = MagicMock()
    client.post = AsyncMock(return_value=_mock_response(400))

    result = await post_with_retry(client, "http://example.com", {}, "svc1")

    assert result is not None
    assert result.status_code == 400
    client.post.assert_called_once()


# ---------------------------------------------------------------------------
# post_with_retry — exhaustion logging (US2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exhaustion_emits_error_log():
    client = MagicMock()
    client.post = AsyncMock(return_value=_mock_response(503))

    with patch("src.recommendation.retry.logger") as mock_logger:
        result = await post_with_retry(client, "http://svc.example.com/rec", {}, "svc1")

    assert result is None
    assert client.post.call_count == 4  # 1 original + 3 retries
    mock_logger.error.assert_called_once()
    call_kwargs = mock_logger.error.call_args[1]
    assert call_kwargs["provider"] == "svc1"
    assert call_kwargs["endpoint"] == "http://svc.example.com/rec"
    assert call_kwargs["http_status"] == 503
    assert call_kwargs["attempts"] == 4


@pytest.mark.asyncio
async def test_exhaustion_on_network_error_emits_log():
    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("src.recommendation.retry.logger") as mock_logger:
        result = await post_with_retry(client, "http://svc.example.com/rec", {}, "svc1")

    assert result is None
    assert client.post.call_count == 4
    mock_logger.error.assert_called_once()
    call_kwargs = mock_logger.error.call_args[1]
    assert call_kwargs["http_status"] is None
    assert call_kwargs["error"] is not None


@pytest.mark.asyncio
async def test_no_log_on_eventual_success():
    client = MagicMock()
    client.post = AsyncMock(
        side_effect=[_mock_response(503), _mock_response(503), _mock_response(200)]
    )

    with patch("src.recommendation.retry.logger") as mock_logger:
        result = await post_with_retry(client, "http://example.com", {}, "svc1")

    assert result is not None
    mock_logger.error.assert_not_called()


# ---------------------------------------------------------------------------
# Adapter integration — Service1 (US1 + US3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service1_retries_on_transient_failure():
    from src.recommendation.adapters.service1_adapter import Service1Adapter

    client = MagicMock()
    client.post = AsyncMock(
        side_effect=[
            _mock_response(500),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=[{"recommendation": "drink water", "confidence": 0.9}]),
            ),
        ]
    )

    adapter = Service1Adapter(client, "http://svc1.example.com", "tok")
    result = await adapter.get_recommendations(170.0, 70.0)

    assert result.error is None
    assert len(result.recommendations) == 1
    assert client.post.call_count == 2


# ---------------------------------------------------------------------------
# Adapter integration — Service2 (US3) — same session_token across retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service2_retries_on_transient_failure():
    from src.recommendation.adapters.service2_adapter import Service2Adapter

    captured_bodies: list[dict] = []

    async def capture_post(url, json=None, **kwargs):  # noqa: ARG001
        captured_bodies.append(json or {})
        if len(captured_bodies) < 3:
            return _mock_response(500)
        return MagicMock(
            status_code=200,
            json=MagicMock(return_value=[{"title": "go for a walk", "priority": 800}]),
        )

    client = MagicMock()
    client.post = capture_post

    adapter = Service2Adapter(client, "http://svc2.example.com")
    result = await adapter.get_recommendations(170.0, 70.0)

    assert result.error is None
    assert len(result.recommendations) == 1
    assert len(captured_bodies) == 3
    # All retries used the same session_token
    tokens = [b.get("session_token") for b in captured_bodies]
    assert tokens[0] == tokens[1] == tokens[2]


# ---------------------------------------------------------------------------
# Adapter integration — DynamicAdapter (US3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_adapter_retries_on_transient_failure():
    from src.recommendation.adapters.dynamic_adapter import DynamicAdapter

    client = MagicMock()
    client.post = AsyncMock(
        side_effect=[
            _mock_response(502),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=[{"advice": "sleep more", "score": 700}]),
            ),
        ]
    )

    adapter = DynamicAdapter(
        http_client=client,
        provider_id="dynamic-svc",
        endpoint_url="http://dynamic.example.com",
        request_mapping={"fields": {"height": "$HEIGHT"}},
        response_mapping={
            "array_path": "",
            "text_field": "advice",
            "score_field": "score",
            "score_multiplier": 1,
        },
    )
    result = await adapter.get_recommendations(170.0, 70.0)

    assert result.error is None
    assert len(result.recommendations) == 1
    assert client.post.call_count == 2
