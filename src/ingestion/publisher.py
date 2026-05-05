import asyncio
import json
from typing import Any

from src.ingestion.interfaces import EventPublisher, IngestionEvent
from src.observability.logging import get_logger

logger = get_logger(__name__)


class KinesisPublisher(EventPublisher):
    """Publishes events to AWS Kinesis using asyncio.to_thread to avoid blocking."""

    def __init__(self, stream_name: str, region: str):
        self._stream_name = stream_name
        self._region = region
        self._client: Any = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("kinesis", region_name=self._region)
        return self._client

    async def publish(self, event: IngestionEvent) -> None:
        record = {
            "event_id": event.event_id,
            "device_id": event.device_id,
            "source_protocol": event.source_protocol.value,
            "event_timestamp": event.event_timestamp.isoformat(),
            "trace_id": event.trace_id,
            "is_anomaly": event.is_anomaly,
            "payload": event.payload,
        }
        data = json.dumps(record).encode()
        client = self._get_client()
        await asyncio.to_thread(
            client.put_record,
            StreamName=self._stream_name,
            Data=data,
            PartitionKey=event.source_protocol.value,
        )
        logger.info("event_published", event_id=event.event_id, stream=self._stream_name)


class LocalRedisStreamsPublisher(EventPublisher):
    """Publishes events to Redis Streams for local development."""

    def __init__(self, redis_url: str, stream_name: str):
        self._redis_url = redis_url
        self._stream_name = stream_name
        self._redis: Any = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(self._redis_url)
        return self._redis

    async def publish(self, event: IngestionEvent) -> None:
        r = await self._get_redis()
        fields = {
            "event_id": event.event_id,
            "device_id": event.device_id,
            "source_protocol": event.source_protocol.value,
            "event_timestamp": event.event_timestamp.isoformat(),
            "trace_id": event.trace_id,
            "is_anomaly": "1" if event.is_anomaly else "0",
            "payload": json.dumps(event.payload),
        }
        await r.xadd(self._stream_name, fields)
        logger.info("event_published_local", event_id=event.event_id, stream=self._stream_name)
