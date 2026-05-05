import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ModelType(str, enum.Enum):
    reranker = "reranker"
    anomaly_detector = "anomaly_detector"


class ModelDeploymentStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    failed = "failed"


class TrainedModel(Base):
    __tablename__ = "ml_trained_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_type: Mapped[ModelType] = mapped_column(Enum(ModelType), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    training_job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    predecessor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ml_trained_models.id"), nullable=True
    )
    ndcg_at_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    deployment_status: Mapped[ModelDeploymentStatus] = mapped_column(
        Enum(ModelDeploymentStatus), nullable=False, default=ModelDeploymentStatus.active
    )
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
