"""Unit tests for TFLiteReranker — T014 (must FAIL before implementation)."""

import struct
from unittest.mock import AsyncMock

import pytest
from src.ml.interfaces import UserEmbedding
from src.ml.reranker import TFLiteReranker
from src.recommendation.normalizer import AggregatedRecommendation


def _make_items(n: int = 3) -> list[AggregatedRecommendation]:
    return [
        AggregatedRecommendation(
            short_text=f"tip {i}", max_score=float(100 - i * 10), providers=["s1"]
        )
        for i in range(n)
    ]


def _make_embedding(device_id: str, dim: int = 8, version: int = 1) -> UserEmbedding:
    vec = struct.pack(f"{dim}f", *[0.1 * i for i in range(dim)])
    import time

    return UserEmbedding(
        device_id=device_id, vector=vec, model_version=version, computed_at=time.time()
    )


@pytest.fixture
def feature_store():
    fs = AsyncMock()
    fs.get_embedding.return_value = _make_embedding("dev-warm")
    return fs


@pytest.fixture
def registry():
    reg = AsyncMock()
    reg.get_active_artifact_path.return_value = None  # no model loaded in unit tests
    reg.get_active_version.return_value = None
    return reg


@pytest.fixture
def reranker(feature_store, registry):
    return TFLiteReranker(feature_store=feature_store, registry=registry, min_telemetry_days=7)


@pytest.mark.asyncio
async def test_warm_user_gets_scored(reranker):
    items = _make_items(3)
    result = await reranker.rerank("dev-warm", items, telemetry_days=14)
    assert len(result) == 3
    # All items get a score (not None) for warm user
    scores = [score for _, score in result]
    assert all(s is not None for s in scores)
    # Scores in [0, 1]
    assert all(0.0 <= s <= 1.0 for s in scores)


@pytest.mark.asyncio
async def test_warm_user_order_changes(reranker):
    """Re-ranking should produce a different order from original for warm user."""
    items = _make_items(5)
    result = await reranker.rerank("dev-warm", items, telemetry_days=30)
    # The reranked list is in score-descending order (may differ from input)
    scores = [score for _, score in result]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_cold_start_returns_raw_order_null_scores(reranker):
    items = _make_items(3)
    result = await reranker.rerank("dev-cold", items, telemetry_days=3)
    assert len(result) == 3
    scores = [score for _, score in result]
    assert all(s is None for s in scores)
    # Items in original order
    texts = [item.short_text for item, _ in result]
    assert texts == ["tip 0", "tip 1", "tip 2"]


@pytest.mark.asyncio
async def test_ml_unavailable_fallback(feature_store, registry):
    """When feature store raises, fall back to raw ordering with None scores."""
    feature_store.get_embedding.side_effect = RuntimeError("Redis down")
    reranker = TFLiteReranker(feature_store=feature_store, registry=registry, min_telemetry_days=7)
    items = _make_items(3)
    result = await reranker.rerank("dev-warm", items, telemetry_days=14)
    assert len(result) == 3
    assert all(score is None for _, score in result)


@pytest.mark.asyncio
async def test_cache_miss_returns_null_scores(feature_store, registry):
    """Cache miss (None embedding) returns raw order with None scores."""
    feature_store.get_embedding.return_value = None
    reranker = TFLiteReranker(feature_store=feature_store, registry=registry, min_telemetry_days=7)
    items = _make_items(3)
    result = await reranker.rerank("dev-warm", items, telemetry_days=14)
    assert all(score is None for _, score in result)


@pytest.mark.asyncio
async def test_empty_items(reranker):
    result = await reranker.rerank("dev-warm", [], telemetry_days=14)
    assert result == []


def test_p99_latency_none_before_calls(reranker):
    assert reranker.get_p99_latency_ms() is None
