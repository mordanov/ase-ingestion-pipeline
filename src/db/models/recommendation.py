import uuid
from datetime import UTC, datetime

from sqlalchemy import ARRAY, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class RecommendationRequest(Base):
    __tablename__ = "recommendation_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False, index=True
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # PII — enriched from profile at call time; never logged
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

    providers_called: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    providers_succeeded: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
