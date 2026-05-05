import asyncio
import json
import struct
import time
from typing import Optional

import redis.asyncio as aioredis

from src.ml.interfaces import FeatureStore, UserEmbedding
from src.observability.logging import get_logger

logger = get_logger(__name__)


class RedisFeatureStore(FeatureStore):
    def __init__(self, redis_url: str, ttl_seconds: int = 300):
        self._redis = aioredis.from_url(redis_url, decode_responses=False)
        self._ttl = ttl_seconds

    def _key(self, device_id: str) -> str:
        return f"ml:embedding:{device_id}"

    async def get_embedding(self, device_id: str) -> Optional[UserEmbedding]:
        raw = await self._redis.get(self._key(device_id))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return UserEmbedding(
                device_id=device_id,
                vector=bytes.fromhex(data["vector_hex"]),
                model_version=data["model_version"],
                computed_at=data["computed_at"],
            )
        except Exception as exc:
            logger.warning("embedding_deserialise_failed", device_id=device_id, error=str(exc))
            return None

    async def set_embedding(self, device_id: str, vector: bytes, model_version: int) -> None:
        data = json.dumps({
            "vector_hex": vector.hex(),
            "model_version": model_version,
            "computed_at": time.time(),
        })
        await self._redis.setex(self._key(device_id), self._ttl, data.encode())
        logger.debug("embedding_cached", device_id=device_id, model_version=model_version)


async def refresh_embeddings_for_all_devices(
    feature_store: "RedisFeatureStore",
    db,
    telemetry_dir: str,
    recommendations_dir: str,
    interval_seconds: int = 150,
    min_telemetry_days: int = 1,
) -> None:
    """Background coroutine: periodically re-computes and caches user embeddings.

    Runs every `interval_seconds` (default: TTL/2 = 150s for default 300s TTL).
    Each iteration queries active devices and writes a fresh embedding for each.
    """
    from sqlalchemy import select
    from src.db.models.device import Device
    from src.ml.training.data_extractor import DataExtractor
    from src.ml.training.feature_engineer import FeatureEngineer
    from src.ml.registry import DbModelRegistry

    registry = DbModelRegistry(db)
    engineer = FeatureEngineer(min_days=min_telemetry_days)
    extractor = DataExtractor(telemetry_dir, recommendations_dir)

    while True:
        try:
            model_version = await registry.get_active_version("reranker") or 0

            telemetry = await extractor.extract_telemetry()
            device_features = await asyncio.to_thread(engineer.build_features, telemetry)
            features_by_device = {df.device_id: df for df in device_features}

            result = await db.execute(select(Device))
            devices = result.scalars().all()

            refreshed = 0
            for device in devices:
                df = features_by_device.get(device.device_id)
                if df is not None:
                    await feature_store.set_embedding(device.device_id, df.vector, model_version)
                    refreshed += 1

            logger.info("embedding_refresh_complete", refreshed=refreshed, model_version=model_version)
        except Exception as exc:
            logger.warning("embedding_refresh_failed", error=str(exc))

        await asyncio.sleep(interval_seconds)
