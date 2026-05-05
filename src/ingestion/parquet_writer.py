"""Writes ingestion events to Hive-partitioned Parquet files.

Directory layout
----------------
<parquet_output_dir>/
  year=YYYY/
    month=MM/
      day=DD/
        source_protocol=http/
          events_<epoch_ms>.parquet
        source_protocol=mqtt/
          events_<epoch_ms>.parquet

Partitioned by the date in event_timestamp.
Sub-partitioned (clustered) by source_protocol as the event type.
Each ingest call appends a new file inside the matching leaf directory.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from src.ingestion.interfaces import IngestionEvent
from src.observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMA = pa.schema([
    pa.field("event_id", pa.string()),
    pa.field("device_id", pa.string()),
    pa.field("source_protocol", pa.string()),
    pa.field("event_timestamp", pa.timestamp("us", tz="UTC")),
    pa.field("trace_id", pa.string()),
    pa.field("is_anomaly", pa.bool_()),
    pa.field("is_stale", pa.bool_()),
    pa.field("is_batch", pa.bool_()),
    pa.field("batch_id", pa.string()),
    pa.field("payload_json", pa.string()),
    pa.field("ingest_at", pa.timestamp("us", tz="UTC")),
])


@dataclass
class EventRecord:
    event: IngestionEvent
    is_stale: bool


class ParquetEventWriter:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def _write_sync(self, records: list[EventRecord]) -> None:
        now = datetime.now(timezone.utc)
        ts_ms = int(time.time() * 1000)

        # Group by (year, month, day, source_protocol) so each Parquet file is
        # homogeneous — one event type, one calendar day.
        groups: dict[tuple[str, str, str, str], list[EventRecord]] = {}
        for rec in records:
            ts = rec.event.event_timestamp
            if not isinstance(ts, datetime):
                ts = datetime.fromisoformat(str(ts))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            proto = rec.event.source_protocol.value
            key = (ts.strftime("%Y"), ts.strftime("%m"), ts.strftime("%d"), proto)
            groups.setdefault(key, []).append(rec)

        for (year, month, day, proto), group in groups.items():
            partition_dir = (
                self._base
                / f"year={year}"
                / f"month={month}"
                / f"day={day}"
                / f"source_protocol={proto}"
            )
            partition_dir.mkdir(parents=True, exist_ok=True)

            rows: list[dict[str, Any]] = []
            for rec in group:
                ts = rec.event.event_timestamp
                if not isinstance(ts, datetime):
                    ts = datetime.fromisoformat(str(ts))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                rows.append({
                    "event_id": rec.event.event_id,
                    "device_id": rec.event.device_id,
                    "source_protocol": proto,
                    "event_timestamp": ts,
                    "trace_id": rec.event.trace_id or "",
                    "is_anomaly": bool(rec.event.is_anomaly),
                    "is_stale": rec.is_stale,
                    "is_batch": bool(rec.event.is_batch),
                    "batch_id": rec.event.batch_id or "",
                    "payload_json": json.dumps(rec.event.payload or {}),
                    "ingest_at": now,
                })

            table = pa.Table.from_pylist(rows, schema=_SCHEMA)
            out_path = partition_dir / f"events_{ts_ms}.parquet"
            pq.write_table(table, out_path)
            logger.info("parquet_written", path=str(out_path), rows=len(rows))

    async def write(self, records: list[EventRecord]) -> None:
        """Run the synchronous Parquet write in a thread pool to avoid blocking the event loop."""
        await asyncio.to_thread(self._write_sync, records)
