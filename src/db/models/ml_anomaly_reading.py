import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AnomalyReading(Base):
    __tablename__ = "ml_anomaly_readings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False, index=True
    )
    reading_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_exceeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluated_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    suppression_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
