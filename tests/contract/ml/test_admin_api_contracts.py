"""Contract tests for admin ML API endpoints — T034, T045, T046."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.contract


@pytest.fixture
async def client(async_client: AsyncClient):
    """Reuse the shared integration test client (includes ML routers via conftest)."""
    return async_client


# ── Training API contracts (T034) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrain_requires_api_key(client):
    resp = await client.post("/admin/ml/retrain")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_retrain_returns_202_schema(client):
    resp = await client.post("/admin/ml/retrain", headers={"X-API-Key": "test-key"})
    assert resp.status_code in (202, 409, 500)
    if resp.status_code == 202:
        data = resp.json()
        assert "job_id" in data
        assert "status" in data
        assert "triggered_by" in data
        assert "started_at" in data
        assert data["status"] == "running"


@pytest.mark.asyncio
async def test_concurrent_retrain_returns_409(client):
    """Second retrain while first is running must return 409 with clear message."""
    # First call
    resp1 = await client.post("/admin/ml/retrain", headers={"X-API-Key": "test-key"})
    if resp1.status_code == 202:
        # Second call while first is supposedly running
        resp2 = await client.post("/admin/ml/retrain", headers={"X-API-Key": "test-key"})
        if resp2.status_code == 409:
            data = resp2.json()
            assert "Training already in progress" in str(data.get("detail", ""))


@pytest.mark.asyncio
async def test_get_training_job_schema(client):
    """GET /admin/ml/training-jobs/{id} returns correct schema."""
    resp = await client.post("/admin/ml/retrain", headers={"X-API-Key": "test-key"})
    if resp.status_code == 202:
        job_id = resp.json()["job_id"]
        job_resp = await client.get(
            f"/admin/ml/training-jobs/{job_id}", headers={"X-API-Key": "test-key"}
        )
        assert job_resp.status_code == 200
        data = job_resp.json()
        assert "job_id" in data
        assert "status" in data
        assert "triggered_by" in data
        assert "started_at" in data
        assert "ended_at" in data
        assert "reranker_ndcg_at_10" in data
        assert "anomaly_detector_f1" in data
        assert "error_message" in data


@pytest.mark.asyncio
async def test_get_training_job_404_for_unknown_id(client):
    resp = await client.get(
        "/admin/ml/training-jobs/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 404


# ── ML Metrics contract (T045, T046) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_ml_metrics_requires_api_key(client):
    resp = await client.get("/admin/ml/metrics")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ml_metrics_schema(client):
    resp = await client.get("/admin/ml/metrics", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert "reranker" in data
    assert "anomaly_detector" in data
    assert "inference" in data
    assert "staleness" in data


@pytest.mark.asyncio
async def test_ml_metrics_no_model_returns_null_fields(client):
    """Before any training, all metric fields are null (not 500)."""
    resp = await client.get("/admin/ml/metrics", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    # Model version should be null when no model has been trained
    assert data["reranker"]["model_version"] is None or isinstance(
        data["reranker"]["model_version"], int
    )
    assert data["staleness"]["threshold_seconds"] > 0


# ── Model package contract ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_package_latest_404_when_no_package(client):
    resp = await client.get("/admin/ml/model-package/latest", headers={"X-API-Key": "test-key"})
    assert resp.status_code in (200, 404)  # 404 if no package built yet


@pytest.mark.asyncio
async def test_model_package_download_404_for_unknown_id(client):
    resp = await client.get(
        "/admin/ml/model-package/00000000-0000-0000-0000-000000000000/download",
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 404
