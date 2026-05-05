import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class SourceProtocol(str, enum.Enum):
    http = "http"
    mqtt = "mqtt"


class ValidationStatus(str, enum.Enum):
    valid = "valid"
    invalid = "invalid"
    stale = "stale"


class BatchStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False, index=True
    )
    batch_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), nullable=False, default=BatchStatus.pending
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False, index=True
    )
    source_protocol: Mapped[SourceProtocol] = mapped_column(Enum(SourceProtocol), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus), nullable=False, default=ValidationStatus.valid
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_batches.id"),
        nullable=True,
    )
