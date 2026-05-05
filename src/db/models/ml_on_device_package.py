import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class OnDeviceModelPackage(Base):
    __tablename__ = "ml_on_device_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reranker_model_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ml_trained_models.id"), nullable=False
    )
    anomaly_detector_model_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ml_trained_models.id"), nullable=False
    )
    package_path: Mapped[str] = mapped_column(String(512), nullable=False)
    compatibility_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    distributed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
