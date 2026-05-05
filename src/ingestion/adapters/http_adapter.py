import uuid
from datetime import datetime
from typing import Any

from src.ingestion.interfaces import IngestionAdapter, IngestionEvent, SourceProtocol
from src.observability.logging import get_logger

logger = get_logger(__name__)


class ValidationError(Exception):
    def __init__(self, field: str, code: str, message: str):
        self.field = field
        self.code = code
        self.message = message
        super().__init__(message)


class HttpIngestionAdapter(IngestionAdapter):
    """Parses Device Simulator single-event and batch payloads into IngestionEvents."""

    async def parse(self, raw: dict[str, Any]) -> list[IngestionEvent]:
        if "events" in raw:
            return self._parse_batch(raw)
        return [self._parse_single(raw)]

    def _parse_single(self, raw: dict[str, Any], batch_id: str | None = None) -> IngestionEvent:
        device_id = raw.get("device_id", "")
        event_id = raw.get("event_id", "")

        if not device_id:
            raise ValidationError("device_id", "MISSING", "device_id is required")
        if not event_id:
            raise ValidationError("event_id", "MISSING", "event_id is required")

        raw_ts = raw.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(raw_ts)
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                "timestamp", "INVALID_TIMESTAMP", f"Cannot parse timestamp: {raw_ts!r}"
            ) from exc

        return IngestionEvent(
            device_id=device_id,
            event_id=event_id,
            source_protocol=SourceProtocol.HTTP,
            event_timestamp=ts,
            payload={
                k: v for k, v in raw.items() if k not in ("device_id", "event_id", "timestamp")
            },
            trace_id=str(uuid.uuid4().hex),
            is_batch=batch_id is not None,
            batch_id=batch_id,
            is_anomaly=bool(raw.get("is_anomaly", False)),
        )

    def _parse_batch(self, raw: dict[str, Any]) -> list[IngestionEvent]:
        batch_id = raw.get("batch_id") or str(uuid.uuid4())
        events = raw.get("events", [])
        if not isinstance(events, list):
            raise ValidationError("events", "INVALID_FORMAT", "events must be a list")
        return [self._parse_single(e, batch_id=batch_id) for e in events]
