"""Integration test for full training pipeline run — T035."""

import os
from datetime import UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models.ml_training_job import TrainingJob, TrainingJobStatus
from src.ml.training.pipeline import TrainingAlreadyRunningError, TrainingPipeline

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pipeline_run_succeeds_and_saves_job(db_session: AsyncSession, tmp_path):
    """Full pipeline run writes a succeeded TrainingJob to the DB."""
    telemetry_dir = str(tmp_path / "delta")
    recommendations_dir = str(tmp_path / "recommendations")
    artifact_dir = str(tmp_path / "models")
    os.makedirs(artifact_dir, exist_ok=True)

    pipeline = TrainingPipeline(
        db=db_session,
        telemetry_dir=telemetry_dir,
        recommendations_dir=recommendations_dir,
        artifact_dir=artifact_dir,
    )
    job = await pipeline.run(triggered_by="test-runner")

    assert job.status == TrainingJobStatus.succeeded
    assert job.ended_at is not None
    assert job.error_message is None


@pytest.mark.asyncio
async def test_pipeline_creates_artifact_files(db_session: AsyncSession, tmp_path):
    """Successful pipeline run writes at least two model artifact files to disk."""
    artifact_dir = str(tmp_path / "models")
    os.makedirs(artifact_dir, exist_ok=True)

    pipeline = TrainingPipeline(
        db=db_session,
        telemetry_dir=str(tmp_path / "delta"),
        recommendations_dir=str(tmp_path / "recs"),
        artifact_dir=artifact_dir,
    )
    await pipeline.run(triggered_by="test-runner")

    artifacts = list(tmp_path.glob("models/**/*"))
    model_files = [f for f in artifacts if f.is_file()]
    assert len(model_files) >= 2, f"Expected ≥2 artifacts, found: {model_files}"


@pytest.mark.asyncio
async def test_pipeline_registers_active_models(db_session: AsyncSession, tmp_path):
    """After a successful run, both model types have an active TrainedModel record."""
    from sqlalchemy import select
    from src.db.models.ml_trained_model import ModelDeploymentStatus, ModelType, TrainedModel

    artifact_dir = str(tmp_path / "models")
    os.makedirs(artifact_dir, exist_ok=True)

    pipeline = TrainingPipeline(
        db=db_session,
        telemetry_dir=str(tmp_path / "delta"),
        recommendations_dir=str(tmp_path / "recs"),
        artifact_dir=artifact_dir,
    )
    job = await pipeline.run(triggered_by="test-runner")
    assert job.status == TrainingJobStatus.succeeded

    reranker_result = await db_session.execute(
        select(TrainedModel).where(
            TrainedModel.model_type == ModelType.reranker,
            TrainedModel.deployment_status == ModelDeploymentStatus.active,
        )
    )
    reranker = reranker_result.scalar_one_or_none()
    assert reranker is not None, "No active reranker model found after training"

    anomaly_result = await db_session.execute(
        select(TrainedModel).where(
            TrainedModel.model_type == ModelType.anomaly_detector,
            TrainedModel.deployment_status == ModelDeploymentStatus.active,
        )
    )
    anomaly = anomaly_result.scalar_one_or_none()
    assert anomaly is not None, "No active anomaly_detector model found after training"


@pytest.mark.asyncio
async def test_concurrent_pipeline_raises(db_session: AsyncSession, tmp_path):
    """Second pipeline.run() while first is in 'running' status raises TrainingAlreadyRunningError."""
    import uuid
    from datetime import datetime

    # Manually insert a running job to simulate concurrent run
    running_job = TrainingJob(
        id=uuid.uuid4(),
        status=TrainingJobStatus.running,
        triggered_by="another-runner",
        started_at=datetime.now(UTC),
    )
    db_session.add(running_job)
    await db_session.commit()

    pipeline = TrainingPipeline(
        db=db_session,
        telemetry_dir=str(tmp_path / "delta"),
        recommendations_dir=str(tmp_path / "recs"),
        artifact_dir=str(tmp_path / "models"),
    )
    with pytest.raises(TrainingAlreadyRunningError):
        await pipeline.run(triggered_by="test-runner")
