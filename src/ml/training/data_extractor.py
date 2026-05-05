import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from src.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TelemetryRecord:
    device_id: str
    event_timestamp: str
    heart_rate: Optional[float]
    steps: Optional[float]
    sleep_duration: Optional[float]
    activity_level: Optional[str]


@dataclass
class RecommendationRecord:
    device_id: str
    provider_id: str
    short_text: str
    score: float
    requested_at: str


class DataExtractor:
    """Reads raw training data from Delta Lake archives."""

    def __init__(self, telemetry_dir: str, recommendations_dir: str):
        self._telemetry_dir = telemetry_dir
        self._recommendations_dir = recommendations_dir

    async def extract_telemetry(self) -> list[TelemetryRecord]:
        """Extract telemetry events from the Delta Lake archive."""
        try:
            records = await asyncio.to_thread(self._read_telemetry_sync)
            logger.info("telemetry_extracted", count=len(records))
            return records
        except Exception as exc:
            logger.warning("telemetry_extract_failed", error=str(exc))
            return []

    async def extract_recommendations(self) -> list[RecommendationRecord]:
        """Extract provider recommendation responses from the archive."""
        try:
            records = await asyncio.to_thread(self._read_recommendations_sync)
            logger.info("recommendations_extracted", count=len(records))
            return records
        except Exception as exc:
            logger.warning("recommendations_extract_failed", error=str(exc))
            return []

    def _read_telemetry_sync(self) -> list[TelemetryRecord]:
        try:
            from deltalake import DeltaTable
            dt = DeltaTable(self._telemetry_dir)
            tbl = dt.to_pyarrow_table()
        except Exception:
            return []

        col = {name: tbl.column(name) for name in tbl.schema.names}
        records = []
        for i in range(tbl.num_rows):
            raw = col["payload_json"][i].as_py()
            try:
                payload = json.loads(raw) if isinstance(raw, str) else {}
            except (TypeError, ValueError):
                payload = {}
            hr = payload.get("heart_rate")
            steps = payload.get("steps")
            sleep = payload.get("sleep")
            records.append(TelemetryRecord(
                device_id=str(col["device_id"][i].as_py() or ""),
                event_timestamp=str(col["event_timestamp"][i].as_py() or ""),
                heart_rate=_to_float(hr.get("bpm") if isinstance(hr, dict) else hr),
                steps=_to_float(steps.get("count") if isinstance(steps, dict) else steps),
                sleep_duration=_to_float(sleep.get("duration_minutes") if isinstance(sleep, dict) else sleep),
                activity_level=payload.get("activity_level"),
            ))
        return records

    def _read_recommendations_sync(self) -> list[RecommendationRecord]:
        try:
            from deltalake import DeltaTable
            dt = DeltaTable(self._recommendations_dir)
            tbl = dt.to_pyarrow_table()
        except Exception:
            return []

        col = {name: tbl.column(name) for name in tbl.schema.names}
        records = []
        for i in range(tbl.num_rows):
            records.append(RecommendationRecord(
                device_id=str(col["device_id"][i].as_py() or ""),
                provider_id=str(col["provider_id"][i].as_py() or ""),
                short_text=str(col["short_text"][i].as_py() or ""),
                score=_to_float(col["normalised_score"][i].as_py(), default=0.0),
                requested_at=str(col["requested_at"][i].as_py() or ""),
            ))
        return records


def _to_float(value, default: float = 0.0) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
