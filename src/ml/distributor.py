import asyncio
import json
import os
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.ml_on_device_package import OnDeviceModelPackage
from src.db.models.ml_trained_model import ModelDeploymentStatus, ModelType, TrainedModel
from src.observability.logging import get_logger

logger = get_logger(__name__)

_MANIFEST_SCHEMA_VERSION = 1
_MIN_TFLITE_VERSION = "2.13.0"


class Distributor:
    """Builds on-device model packages (ZIP with manifest) for device sync distribution."""

    def __init__(self, db: AsyncSession, package_dir: str):
        self._db = db
        self._package_dir = package_dir

    async def build_package(self) -> Optional[OnDeviceModelPackage]:
        """Build a new distribution package from the currently active models.

        Returns the persisted OnDeviceModelPackage or None if models are not available.
        """
        reranker = await self._get_active(ModelType.reranker)
        anomaly_model = await self._get_active(ModelType.anomaly_detector)

        if reranker is None or anomaly_model is None:
            logger.warning("distributor_no_active_models")
            return None

        os.makedirs(self._package_dir, exist_ok=True)

        filename = (
            f"ml_package_v{reranker.version}_{anomaly_model.version}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
        )
        package_path = os.path.join(self._package_dir, filename)

        await asyncio.to_thread(
            self._write_zip,
            package_path,
            reranker,
            anomaly_model,
        )

        metadata = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "min_tflite_runtime_version": _MIN_TFLITE_VERSION,
            "reranker_input_dim": self._infer_dim(reranker),
            "anomaly_input_dim": self._infer_dim(anomaly_model),
        }

        record = OnDeviceModelPackage(
            id=uuid.uuid4(),
            reranker_model_id=reranker.id,
            anomaly_detector_model_id=anomaly_model.id,
            package_path=package_path,
            compatibility_metadata=metadata,
        )
        self._db.add(record)
        await self._db.flush()
        logger.info(
            "package_built",
            path=package_path,
            reranker_version=reranker.version,
            anomaly_version=anomaly_model.version,
        )
        return record

    async def _get_active(self, model_type: ModelType) -> Optional[TrainedModel]:
        result = await self._db.execute(
            select(TrainedModel).where(
                TrainedModel.model_type == model_type,
                TrainedModel.deployment_status == ModelDeploymentStatus.active,
            )
        )
        return result.scalar_one_or_none()

    def _write_zip(
        self, path: str, reranker: TrainedModel, anomaly_model: TrainedModel
    ) -> None:
        manifest = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reranker": {
                "version": reranker.version,
                "input_dim": self._infer_dim(reranker),
                "output_dim": 1,
                "filename": "reranker.tflite",
            },
            "anomaly_detector": {
                "version": anomaly_model.version,
                "input_dim": self._infer_dim(anomaly_model),
                "output_dim": 1,
                "filename": "anomaly_detector.tflite",
            },
            "compatibility": {
                "min_tflite_runtime_version": _MIN_TFLITE_VERSION,
                "supported_platforms": ["android", "ios", "linux-arm64"],
            },
        }

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # Write model artifacts (from their stored paths)
            for artifact_path, arc_name in [
                (reranker.artifact_path, "reranker.tflite"),
                (anomaly_model.artifact_path, "anomaly_detector.tflite"),
            ]:
                if os.path.exists(artifact_path):
                    zf.write(artifact_path, arc_name)
                else:
                    # Write a placeholder if artifact not found (PoC fallback)
                    zf.writestr(arc_name, b"")

    def _infer_dim(self, model: TrainedModel) -> int:
        return 64 if model.model_type == ModelType.reranker else 16

    async def get_latest_package(self) -> Optional[OnDeviceModelPackage]:
        result = await self._db.execute(
            select(OnDeviceModelPackage).order_by(OnDeviceModelPackage.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
