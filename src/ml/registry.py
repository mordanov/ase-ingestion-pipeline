from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.ml_trained_model import ModelDeploymentStatus, ModelType, TrainedModel
from src.ml.interfaces import ModelRegistry
from src.observability.logging import get_logger

logger = get_logger(__name__)


class DbModelRegistry(ModelRegistry):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_active_artifact_path(self, model_type: str) -> Optional[str]:
        model = await self._get_active(model_type)
        return model.artifact_path if model else None

    async def get_active_version(self, model_type: str) -> Optional[int]:
        model = await self._get_active(model_type)
        return model.version if model else None

    async def _get_active(self, model_type: str) -> Optional[TrainedModel]:
        result = await self._db.execute(
            select(TrainedModel).where(
                TrainedModel.model_type == ModelType(model_type),
                TrainedModel.deployment_status == ModelDeploymentStatus.active,
            )
        )
        return result.scalar_one_or_none()

    async def register_model(
        self,
        model_type: str,
        artifact_path: str,
        training_job_id: str,
        ndcg_at_10: Optional[float] = None,
        f1_score: Optional[float] = None,
    ) -> int:
        """Register a new model, archive the previous active one, return new model id."""
        prev = await self._get_active(model_type)
        if prev:
            prev.deployment_status = ModelDeploymentStatus.archived
            predecessor_id = prev.id
            next_version = prev.version + 1
        else:
            predecessor_id = None
            next_version = 1

        model = TrainedModel(
            model_type=ModelType(model_type),
            version=next_version,
            training_job_id=training_job_id,
            artifact_path=artifact_path,
            predecessor_id=predecessor_id,
            ndcg_at_10=ndcg_at_10,
            f1_score=f1_score,
            deployment_status=ModelDeploymentStatus.active,
            deployed_at=datetime.now(timezone.utc),
        )
        self._db.add(model)
        await self._db.flush()
        logger.info(
            "model_registered",
            model_type=model_type,
            version=next_version,
            artifact_path=artifact_path,
        )
        return model.id

    async def rollback(self, model_type: str) -> bool:
        """Re-activate the predecessor of the current active model (FR-020)."""
        current = await self._get_active(model_type)
        if not current or current.predecessor_id is None:
            return False

        pred_result = await self._db.execute(
            select(TrainedModel).where(TrainedModel.id == current.predecessor_id)
        )
        predecessor = pred_result.scalar_one_or_none()
        if predecessor is None:
            return False

        current.deployment_status = ModelDeploymentStatus.archived
        predecessor.deployment_status = ModelDeploymentStatus.active
        predecessor.deployed_at = datetime.now(timezone.utc)
        logger.info("model_rollback", model_type=model_type, rolled_back_to_version=predecessor.version)
        return True
