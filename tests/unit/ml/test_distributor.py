"""Unit tests for Distributor — T026 (must FAIL before implementation)."""
import json
import os
import struct
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models.ml_trained_model import ModelDeploymentStatus, ModelType, TrainedModel
from src.ml.distributor import Distributor


def _make_model(model_type: ModelType, version: int, artifact_path: str) -> TrainedModel:
    m = MagicMock(spec=TrainedModel)
    m.id = 1
    m.model_type = model_type
    m.version = version
    m.artifact_path = artifact_path
    m.deployment_status = ModelDeploymentStatus.active
    return m


@pytest.fixture
def tmp_dirs():
    with tempfile.TemporaryDirectory() as models_dir, tempfile.TemporaryDirectory() as packages_dir:
        yield models_dir, packages_dir


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_build_package_creates_zip(tmp_dirs, mock_db):
    models_dir, packages_dir = tmp_dirs

    # Create stub model files
    reranker_path = os.path.join(models_dir, "reranker.model")
    anomaly_path = os.path.join(models_dir, "anomaly.model")
    with open(reranker_path, "wb") as f:
        f.write(struct.pack("8f", *[0.1] * 8))
    with open(anomaly_path, "wb") as f:
        f.write(struct.pack("4f", *[0.2] * 4))

    reranker_model = _make_model(ModelType.reranker, version=3, artifact_path=reranker_path)
    anomaly_model = _make_model(ModelType.anomaly_detector, version=3, artifact_path=anomaly_path)

    # Mock DB to return active models
    results = [MagicMock(), MagicMock()]
    results[0].scalar_one_or_none.return_value = reranker_model
    results[1].scalar_one_or_none.return_value = anomaly_model
    mock_db.execute = AsyncMock(side_effect=results)

    distributor = Distributor(db=mock_db, package_dir=packages_dir)
    package = await distributor.build_package()

    assert package is not None
    assert os.path.exists(package.package_path)
    assert package.package_path.endswith(".zip")


@pytest.mark.asyncio
async def test_zip_contains_manifest(tmp_dirs, mock_db):
    models_dir, packages_dir = tmp_dirs

    reranker_path = os.path.join(models_dir, "reranker.model")
    anomaly_path = os.path.join(models_dir, "anomaly.model")
    for p in [reranker_path, anomaly_path]:
        with open(p, "wb") as f:
            f.write(b"\x00" * 16)

    reranker_model = _make_model(ModelType.reranker, version=5, artifact_path=reranker_path)
    anomaly_model = _make_model(ModelType.anomaly_detector, version=5, artifact_path=anomaly_path)

    results = [MagicMock(), MagicMock()]
    results[0].scalar_one_or_none.return_value = reranker_model
    results[1].scalar_one_or_none.return_value = anomaly_model
    mock_db.execute = AsyncMock(side_effect=results)

    distributor = Distributor(db=mock_db, package_dir=packages_dir)
    package = await distributor.build_package()

    with zipfile.ZipFile(package.package_path) as zf:
        assert "manifest.json" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))

    assert manifest["schema_version"] == 1
    assert manifest["reranker"]["version"] == 5
    assert manifest["anomaly_detector"]["version"] == 5
    assert "compatibility" in manifest
    assert "min_tflite_runtime_version" in manifest["compatibility"]


@pytest.mark.asyncio
async def test_build_package_returns_none_when_no_models(mock_db, tmp_dirs):
    _, packages_dir = tmp_dirs
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    distributor = Distributor(db=mock_db, package_dir=packages_dir)
    package = await distributor.build_package()
    assert package is None
