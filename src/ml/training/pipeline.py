import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.ml_training_job import TrainingJob, TrainingJobStatus
from src.ml.registry import DbModelRegistry
from src.ml.training.data_extractor import DataExtractor
from src.ml.training.evaluator import Evaluator
from src.ml.training.feature_engineer import FeatureEngineer
from src.ml.training.model_trainer import ModelTrainer
from src.observability.logging import get_logger

logger = get_logger(__name__)


class TrainingAlreadyRunningError(Exception):
    def __init__(self, active_job_id: str):
        self.active_job_id = active_job_id
        super().__init__(f"Training already in progress: {active_job_id}")


class TrainingPipeline:
    """Orchestrates the full ML training pipeline (FR-013, FR-014)."""

    def __init__(
        self,
        db: AsyncSession,
        telemetry_dir: str,
        recommendations_dir: str,
        artifact_dir: str,
        package_dir: Optional[str] = None,
        min_telemetry_days: int = 1,
    ):
        self._db = db
        self._extractor = DataExtractor(telemetry_dir, recommendations_dir)
        self._engineer = FeatureEngineer(min_days=min_telemetry_days)
        self._trainer = ModelTrainer(artifact_dir)
        self._evaluator = Evaluator()
        self._registry = DbModelRegistry(db)
        self._package_dir = package_dir

    async def run(self, triggered_by: str) -> TrainingJob:
        """Run the full training pipeline.

        Raises TrainingAlreadyRunningError if a job is already in progress (FR-016).
        """
        await self._assert_no_running_job()

        job_id = uuid.uuid4()
        job = TrainingJob(
            id=job_id,
            status=TrainingJobStatus.running,
            triggered_by=triggered_by,
            started_at=datetime.now(timezone.utc),
        )
        self._db.add(job)
        await self._db.commit()

        logger.info("training_pipeline_started", job_id=str(job_id), triggered_by=triggered_by)

        try:
            await self._execute_pipeline(job)
        except Exception as exc:
            logger.error("training_pipeline_failed", job_id=str(job_id), error=str(exc))
            await self._fail_job(job, str(exc))

        return job

    async def _assert_no_running_job(self) -> None:
        result = await self._db.execute(
            select(TrainingJob).where(TrainingJob.status == TrainingJobStatus.running)
        )
        running = result.scalar_one_or_none()
        if running is not None:
            raise TrainingAlreadyRunningError(str(running.id))

    async def _execute_pipeline(self, job: TrainingJob) -> None:
        job_id_str = str(job.id)

        # Step 1: Extract data
        logger.info("pipeline_step", job_id=job_id_str, step="data_extraction")
        telemetry = await self._extractor.extract_telemetry()
        recommendations = await self._extractor.extract_recommendations()

        # Step 2: Feature engineering
        logger.info("pipeline_step", job_id=job_id_str, step="feature_engineering")
        device_features = await asyncio.to_thread(self._engineer.build_features, telemetry)

        # Step 3: Model training (both models in one run, FR-014)
        logger.info("pipeline_step", job_id=job_id_str, step="model_training")
        reranker_artifact, anomaly_artifact = await asyncio.to_thread(
            self._train_both, device_features, job_id_str
        )

        # Step 4: Evaluate
        logger.info("pipeline_step", job_id=job_id_str, step="evaluation")
        # Artifacts already contain evaluation metrics from ModelTrainer

        # Step 5: Register models
        logger.info("pipeline_step", job_id=job_id_str, step="model_registration")
        reranker_id = await self._registry.register_model(
            model_type="reranker",
            artifact_path=reranker_artifact.artifact_path,
            training_job_id=job_id_str,
            ndcg_at_10=reranker_artifact.ndcg_at_10,
        )
        anomaly_id = await self._registry.register_model(
            model_type="anomaly_detector",
            artifact_path=anomaly_artifact.artifact_path,
            training_job_id=job_id_str,
            f1_score=anomaly_artifact.f1_score,
        )

        # Mark job succeeded
        job.status = TrainingJobStatus.succeeded
        job.ended_at = datetime.now(timezone.utc)
        job.reranker_model_id = reranker_id
        job.anomaly_detector_model_id = anomaly_id
        job.reranker_ndcg_at_10 = reranker_artifact.ndcg_at_10
        job.anomaly_detector_f1 = anomaly_artifact.f1_score
        await self._db.commit()

        duration_s = (job.ended_at - job.started_at).total_seconds()
        logger.info(
            "training_pipeline_succeeded",
            job_id=job_id_str,
            duration_seconds=duration_s,
            reranker_ndcg=reranker_artifact.ndcg_at_10,
            anomaly_f1=anomaly_artifact.f1_score,
            triggered_by=job.triggered_by,
        )

        # Update Prometheus gauges
        _update_ml_gauges(reranker_artifact.ndcg_at_10, anomaly_artifact.f1_score)

        # Build on-device distribution package if package_dir configured (T053)
        if self._package_dir:
            try:
                from src.ml.distributor import Distributor
                distributor = Distributor(db=self._db, package_dir=self._package_dir)
                await distributor.build_package()
            except Exception as exc:
                logger.warning("distributor_build_failed", job_id=job_id_str, error=str(exc))

    def _train_both(self, device_features, job_id_str):
        reranker_artifact = self._trainer.train_reranker(device_features, job_id_str)
        anomaly_artifact = self._trainer.train_anomaly_detector(device_features, job_id_str)
        return reranker_artifact, anomaly_artifact

    async def _fail_job(self, job: TrainingJob, error: str) -> None:
        job.status = TrainingJobStatus.failed
        job.ended_at = datetime.now(timezone.utc)
        job.error_message = error
        await self._db.commit()
        logger.info(
            "training_job_failed",
            job_id=str(job.id),
            error=error,
            triggered_by=job.triggered_by,
        )


def _update_ml_gauges(ndcg: Optional[float], f1: Optional[float]) -> None:
    try:
        from src.observability.metrics import (
            ML_RERANKER_NDCG_AT_10,
            ML_ANOMALY_F1_SCORE,
            ML_MODEL_STALENESS_SECONDS,
        )
        if ndcg is not None:
            ML_RERANKER_NDCG_AT_10.set(ndcg)
        if f1 is not None:
            ML_ANOMALY_F1_SCORE.set(f1)
        ML_MODEL_STALENESS_SECONDS.set(0)
    except Exception:
        pass
