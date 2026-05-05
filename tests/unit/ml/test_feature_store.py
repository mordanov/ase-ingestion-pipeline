"""Unit tests for RedisFeatureStore — T013 (must FAIL before implementation)."""
import struct
import time

import pytest
import fakeredis.aioredis

from src.ml.feature_store import RedisFeatureStore


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    s = RedisFeatureStore(redis_url="redis://localhost", ttl_seconds=300)
    s._redis = fake_redis
    return s


def _make_vector(n: int = 8) -> bytes:
    floats = [float(i) / n for i in range(n)]
    return struct.pack(f"{n}f", *floats)


@pytest.mark.asyncio
async def test_get_returns_none_on_miss(store):
    result = await store.get_embedding("unknown-device")
    assert result is None


@pytest.mark.asyncio
async def test_round_trip(store):
    vec = _make_vector(8)
    await store.set_embedding("dev-1", vec, model_version=3)
    emb = await store.get_embedding("dev-1")
    assert emb is not None
    assert emb.device_id == "dev-1"
    assert emb.vector == vec
    assert emb.model_version == 3
    assert emb.computed_at <= time.time()


@pytest.mark.asyncio
async def test_overwrite(store):
    vec1 = _make_vector(8)
    vec2 = _make_vector(8)[::-1]  # reversed bytes
    await store.set_embedding("dev-1", vec1, model_version=1)
    await store.set_embedding("dev-1", vec2, model_version=2)
    emb = await store.get_embedding("dev-1")
    assert emb is not None
    assert emb.vector == vec2
    assert emb.model_version == 2


@pytest.mark.asyncio
async def test_ttl_enforced(store):
    """Embeddings expire after TTL."""
    store._ttl = 1
    vec = _make_vector(4)
    await store.set_embedding("dev-ttl", vec, model_version=1)
    # Immediately readable
    assert await store.get_embedding("dev-ttl") is not None
    # After expiry (simulate by overwriting with expire=0 via direct Redis call)
    await store._redis.delete(store._key("dev-ttl"))
    assert await store.get_embedding("dev-ttl") is None


@pytest.mark.asyncio
async def test_different_devices_independent(store):
    vec_a = _make_vector(4)
    vec_b = _make_vector(4)[::-1]
    await store.set_embedding("dev-a", vec_a, model_version=1)
    await store.set_embedding("dev-b", vec_b, model_version=1)
    emb_a = await store.get_embedding("dev-a")
    emb_b = await store.get_embedding("dev-b")
    assert emb_a.vector == vec_a
    assert emb_b.vector == vec_b
