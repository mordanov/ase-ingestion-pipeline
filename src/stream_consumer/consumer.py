from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import boto3

from src.observability.logging import get_logger

logger = get_logger(__name__)

HandlerFn = Callable[[dict], Awaitable[None]]


class KinesisConsumer:
    """Background task that polls Kinesis GetRecords and routes events to a handler."""

    def __init__(
        self,
        stream_name: str,
        region: str,
        handler: HandlerFn,
        poll_interval: float = 0.2,
        shard_iterator_type: str = "LATEST",
    ) -> None:
        self._stream_name = stream_name
        self._region = region
        self._handler = handler
        self._poll_interval = poll_interval
        self._shard_iterator_type = shard_iterator_type
        self._running = False
        self._client = boto3.client("kinesis", region_name=region)

    async def start(self) -> None:
        self._running = True
        try:
            shards = await asyncio.to_thread(self._describe_shards)
        except Exception as exc:
            logger.error("kinesis_describe_shards_failed", error=str(exc))
            return

        tasks = [asyncio.create_task(self._poll_shard(shard["ShardId"])) for shard in shards]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        self._running = False

    def _describe_shards(self) -> list[dict]:
        self._client.describe_stream_summary(StreamName=self._stream_name)
        resp2 = self._client.list_shards(StreamName=self._stream_name)
        return resp2["Shards"]

    async def _poll_shard(self, shard_id: str) -> None:
        try:
            iterator = await asyncio.to_thread(self._get_shard_iterator, shard_id)
        except Exception as exc:
            logger.error("kinesis_get_iterator_failed", shard_id=shard_id, error=str(exc))
            return

        while self._running:
            try:
                records, next_iterator = await asyncio.to_thread(self._get_records, iterator)
                for record in records:
                    await self._process_record(record)
                if next_iterator:
                    iterator = next_iterator
            except Exception as exc:
                logger.error("kinesis_poll_error", shard_id=shard_id, error=str(exc))
                await asyncio.sleep(self._poll_interval * 5)
                continue

            await asyncio.sleep(self._poll_interval)

    def _get_shard_iterator(self, shard_id: str) -> str:
        resp = self._client.get_shard_iterator(
            StreamName=self._stream_name,
            ShardId=shard_id,
            ShardIteratorType=self._shard_iterator_type,
        )
        return resp["ShardIterator"]

    def _get_records(self, iterator: str) -> tuple[list[dict], str | None]:
        resp = self._client.get_records(ShardIterator=iterator, Limit=100)
        return resp.get("Records", []), resp.get("NextShardIterator")

    async def _process_record(self, record: dict) -> None:
        try:
            data = json.loads(record["Data"])
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("kinesis_invalid_record", error=str(exc))
            return

        try:
            await self._handler(data)
        except Exception as exc:
            logger.error(
                "kinesis_handler_error", sequence=record.get("SequenceNumber"), error=str(exc)
            )
