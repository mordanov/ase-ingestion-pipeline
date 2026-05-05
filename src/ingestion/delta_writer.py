"""Appends ingestion events to a Delta Lake table.

Directory layout
----------------
<delta_output_dir>/
  _delta_log/
    00000000000000000000.json   ← transaction log
    00000000000000000001.json
    …
  year=2026/month=05/day=05/source_protocol=http/
    part-<uuid>-0.parquet       ← managed by Delta
  year=2026/month=05/day=05/source_protocol=mqtt/
    …

Every ingest call appends one transaction to the log instead of creating a
new standalone file, so the file count stays manageable.  Run
`make compact-delta` to bin-pack accumulated small part-files after a busy
period.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
from deltalake import write_deltalake

from src.ingestion.interfaces import IngestionEvent
from src.observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMA = pa.schema([
    pa.field("event_id", pa.string()),
    pa.field("device_id", pa.string()),
    pa.field("source_protocol", pa.string()),
    pa.field("year", pa.string()),
    pa.field("month", pa.string()),
    pa.field("day", pa.string()),
    pa.field("event_timestamp", pa.timestamp("us", tz="UTC")),
    pa.field("trace_id", pa.string()),
    pa.field("is_anomaly", pa.bool_()),
    pa.field("is_stale", pa.bool_()),
    pa.field("is_batch", pa.bool_()),
    pa.field("batch_id", pa.string()),
    pa.field("payload_json", pa.string()),
    pa.field("ingest_at", pa.timestamp("us", tz="UTC")),
])

# Partition hierarchy: date first, then event type
_PARTITION_BY = ["year", "month", "day", "source_protocol"]


@dataclass
class EventRecord:
    event: IngestionEvent
    is_stale: bool


class DeltaEventWriter:
    def __init__(self, base_dir: str) -> None:
        self._base = base_dir

    def _write_sync(self, records: list[EventRecord]) -> None:
        now = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        for rec in records:
            ts = rec.event.event_timestamp
            if not isinstance(ts, datetime):
                ts = datetime.fromisoformat(str(ts))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rows.append({
                "event_id": rec.event.event_id,
                "device_id": rec.event.device_id,
                "source_protocol": rec.event.source_protocol.value,
                "year": ts.strftime("%Y"),
                "month": ts.strftime("%m"),
                "day": ts.strftime("%d"),
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
        write_deltalake(
            self._base,
            table,
            mode="append",
            partition_by=_PARTITION_BY,
        )
        logger.info("delta_appended", rows=len(rows))

    async def write(self, records: list[EventRecord]) -> None:
        """Run the synchronous Delta write in a thread pool."""
        await asyncio.to_thread(self._write_sync, records)
