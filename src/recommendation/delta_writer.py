"""Appends raw per-provider recommendations to a Delta Lake table.

Directory layout
----------------
<recommendations_delta_dir>/
  _delta_log/
    00000000000000000000.json
    …
  year=2026/month=05/day=05/provider_id=service1/
    part-<uuid>-0.parquet
  year=2026/month=05/day=05/provider_id=service2/
    …

One row per raw recommendation per provider call.  Partitioned by date and
provider so queries like "all service1 recs on 2026-05-05" hit a single leaf.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
from deltalake import write_deltalake

from src.recommendation.interfaces import RawRecommendation
from src.observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMA = pa.schema([
    pa.field("trace_id", pa.string()),
    pa.field("device_id", pa.string()),
    pa.field("provider_id", pa.string()),
    pa.field("short_text", pa.string()),
    pa.field("normalised_score", pa.float64()),
    pa.field("detail", pa.string()),
    pa.field("year", pa.string()),
    pa.field("month", pa.string()),
    pa.field("day", pa.string()),
    pa.field("requested_at", pa.timestamp("us", tz="UTC")),
])

_PARTITION_BY = ["year", "month", "day", "provider_id"]


@dataclass
class RecommendationRecord:
    trace_id: str
    device_id: str
    provider_id: str
    recommendations: list[RawRecommendation]
    requested_at: datetime


class DeltaRecommendationWriter:
    def __init__(self, base_dir: str) -> None:
        self._base = base_dir

    def _write_sync(self, records: list[RecommendationRecord]) -> None:
        rows: list[dict[str, Any]] = []
        for rec in records:
            ts = rec.requested_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            year = ts.strftime("%Y")
            month = ts.strftime("%m")
            day = ts.strftime("%d")
            for raw in rec.recommendations:
                rows.append({
                    "trace_id": rec.trace_id,
                    "device_id": rec.device_id,
                    "provider_id": rec.provider_id,
                    "short_text": raw.short_text,
                    "normalised_score": raw.normalised_score,
                    "detail": raw.detail or "",
                    "year": year,
                    "month": month,
                    "day": day,
                    "requested_at": ts,
                })

        if not rows:
            return

        table = pa.Table.from_pylist(rows, schema=_SCHEMA)
        write_deltalake(
            self._base,
            table,
            mode="append",
            partition_by=_PARTITION_BY,
        )
        logger.info("recommendations_delta_appended", rows=len(rows))

    async def write(self, records: list[RecommendationRecord]) -> None:
        await asyncio.to_thread(self._write_sync, records)
