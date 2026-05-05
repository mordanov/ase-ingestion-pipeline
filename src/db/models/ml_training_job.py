import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class TrainingJobStatus(enum.StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class TrainingJob(Base):
    __tablename__ = "ml_training_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[TrainingJobStatus] = mapped_column(
        Enum(TrainingJobStatus), nullable=False, default=TrainingJobStatus.running
    )
    triggered_by: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    reranker_model_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ml_trained_models.id"), nullable=True
    )
    anomaly_detector_model_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ml_trained_models.id"), nullable=True
    )
    reranker_ndcg_at_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_detector_f1: Mapped[float | None] = mapped_column(Float, nullable=True)
