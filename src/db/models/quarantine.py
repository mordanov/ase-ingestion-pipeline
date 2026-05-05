import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class QuarantineRecord(Base):
    __tablename__ = "quarantine_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("devices.device_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
