from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Device, QuarantineRecord, TelemetryEvent
from src.db.models.disabled_device import DisabledDevice
from src.ingestion.interfaces import IngestionEvent
from src.observability.logging import get_logger

logger = get_logger(__name__)

STALE_THRESHOLD_HOURS = 24


class ValidationError(Exception):
    def __init__(self, field: str, code: str, message: str):
        self.field = field
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ValidationResult:
    is_valid: bool
    is_stale: bool = False
    is_anomaly: bool = False
    error_code: str | None = None
    error_message: str | None = None


async def validate_event(event: IngestionEvent, session: AsyncSession) -> ValidationResult:
    """Validate a parsed IngestionEvent. Returns ValidationResult or raises ValidationError."""

    if not event.device_id:
        raise ValidationError("device_id", "MISSING", "device_id is required")

    if not event.event_id:
        raise ValidationError("event_id", "MISSING", "event_id is required")

    # Check if device exists
    result = await session.execute(
        select(Device.device_id).where(Device.device_id == event.device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        return ValidationResult(is_valid=False, error_code="UNKNOWN_DEVICE", error_message=f"Device {event.device_id!r} not registered")

    disabled = await session.scalar(
        select(DisabledDevice).where(DisabledDevice.device_id == event.device_id)
    )
    if disabled is not None:
        return ValidationResult(is_valid=False, error_code="DEVICE_DISABLED", error_message=f"Device {event.device_id!r} is disabled")

    # Check staleness
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STALE_THRESHOLD_HOURS)
    ts = event.event_timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    is_stale = ts < cutoff

    is_anomaly = event.is_anomaly or bool(event.payload.get("is_anomaly", False))

    return ValidationResult(is_valid=True, is_stale=is_stale, is_anomaly=is_anomaly)


async def quarantine_event(event: IngestionEvent, error_code: str, error_message: str, session: AsyncSession) -> None:
    # Only set device_id FK when the device is known to exist; unknown/missing devices use NULL
    fk_device_id = None if error_code in ("UNKNOWN_DEVICE", "MISSING") else (event.device_id or None)
    record = QuarantineRecord(
        device_id=fk_device_id,
        raw_payload=event.payload,
        validation_errors={"code": error_code, "message": error_message},
        source_protocol=event.source_protocol.value,
        trace_id=event.trace_id,
    )
    session.add(record)
    await session.flush()
    logger.warning("event_quarantined", event_id=event.event_id, code=error_code)
