# Quickstart: ML Recommendation System

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)  
**Time to first retrain + dashboard**: ~15 minutes

---

## Prerequisites

- Docker and Docker Compose installed
- `make` available
- The existing platform is already running (`docker compose up -d`)
- Python 3.11+ with `uv` or `pip` for local script usage

---

## Step 1 — Start the platform

```bash
make dev
```

This starts all services (PostgreSQL, Redis, FastAPI, Grafana) and creates the data volumes. Wait for the health check to pass:

```bash
curl -s http://localhost:8000/health | python -m json.tool
# Expect: {"status": "ok"}
```

---

## Step 2 — Seed sample data

The ML training pipeline requires at least 7 days of telemetry history per user. Seed the database with enough sample data:

```bash
make seed
```

This registers 10 devices and generates synthetic telemetry events spanning 30 days. The data is written to both PostgreSQL and the Delta Lake archive at `./data/delta`.

---

## Step 3 — Trigger model training

Call the admin API to start the training pipeline:

```bash
curl -s -X POST http://localhost:8000/admin/ml/retrain \
  -H "X-API-Key: dev-key" | python -m json.tool
```

Expected response (202 Accepted):

```json
{
  "job_id": "550e8400-...",
  "status": "running",
  "triggered_by": "admin",
  "started_at": "2026-05-05T14:23:00Z"
}
```

---

## Step 4 — Monitor training progress

Poll the job status using the `job_id` from Step 3:

```bash
JOB_ID="550e8400-..."

watch -n 10 "curl -s http://localhost:8000/admin/ml/training-jobs/$JOB_ID \
  -H 'X-API-Key: dev-key' | python -m json.tool"
```

Training completes in under 60 minutes. A succeeded response looks like:

```json
{
  "job_id": "550e8400-...",
  "status": "succeeded",
  "reranker_ndcg_at_10": 0.743,
  "anomaly_detector_f1": 0.851,
  "ended_at": "2026-05-05T15:10:00Z"
}
```

---

## Step 5 — Verify ML metrics dashboard

Open the metrics endpoint to confirm all four monitoring values are populated:

```bash
curl -s http://localhost:8000/admin/ml/metrics \
  -H "X-API-Key: dev-key" | python -m json.tool
```

All four sections (`reranker`, `anomaly_detector`, `inference`, `staleness`) should show non-null values.

For the Grafana dashboard, open `http://localhost:3000` (default credentials: `admin`/`admin`) and navigate to the **ML Monitoring** dashboard.

---

## Step 6 — Test personalised recommendations

Request recommendations for a seeded device (replace `{device_id}` with a UUID from `make seed` output):

```bash
curl -s -X POST "http://localhost:8000/api/v1/devices/{device_id}/recommendations" \
  -H "X-API-Key: dev-key" | python -m json.tool
```

Each recommendation item in the response will include a `personal_relevance_score` (non-null for users with 7+ days of history) and an `anomaly_suppressed` flag.

---

## Step 7 — Test cold-start fallback

Request recommendations for a device with no telemetry history:

```bash
# Register a new device (no history)
curl -s -X POST http://localhost:8000/api/v1/devices \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "cold-start-test-001", "name": "cold-start-test", "height_cm": 175, "weight_kg": 70}' \
  | python -m json.tool

# Request recommendations — personal_relevance_score should be null
curl -s -X POST "http://localhost:8000/api/v1/devices/cold-start-test-001/recommendations" \
  -H "X-API-Key: dev-key" | python -m json.tool
```

Verify that `personal_relevance_score` is `null` for all items and the response is returned without error.

---

## Step 8 — Test anomaly suppression

Send a telemetry reading with an anomalous heart rate (well above the seeded baseline of ~75 bpm):

```bash
curl -s -X POST http://localhost:8000/ingest/batch \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "event_id": "anomaly-test-001",
      "device_id": "{device_id}",
      "device_type": "smartwatch",
      "user_id": "user-001",
      "timestamp": "2026-05-05T12:00:00Z",
      "heart_rate": {"bpm": 195, "hrv_ms": 10.0},
      "spo2": {"percentage": 96.0}
    }]
  }'

# Then request recommendations
curl -s -X POST "http://localhost:8000/api/v1/devices/{device_id}/recommendations" \
  -H "X-API-Key: dev-key" | python -m json.tool
```

Activity-intensification recommendations should have `anomaly_suppressed: true` or be absent from the list.

---

## Step 9 — Inspect the on-device model package

After training, the distributor builds a ZIP package. Verify it was created:

```bash
curl -s http://localhost:8000/admin/ml/model-package/latest \
  -H "X-API-Key: dev-key" | python -m json.tool
```

Download it and inspect the manifest:

```bash
PACKAGE_ID="..."
curl -s "http://localhost:8000/admin/ml/model-package/$PACKAGE_ID/download" \
  -H "X-API-Key: dev-key" -o /tmp/ml_package.zip

unzip -p /tmp/ml_package.zip manifest.json | python -m json.tool
```

---

## Running Tests

```bash
# Unit tests only
pytest tests/unit/ml/ -v

# Integration tests (requires running PostgreSQL + Redis)
pytest tests/integration/ml/ -v

# Full suite
pytest tests/ -v
```

---

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Training returns 409 immediately | A training job is already running | Wait for it to complete, or check `GET /admin/ml/training-jobs/{id}` |
| `reranker_ndcg_at_10: null` after success | Fewer than 100 users with 7+ days history in the seed data | Re-run `make seed` with a larger `SEED_DEVICE_COUNT` in `.env` |
| `personal_relevance_score` is null for all users | No active model deployed | Trigger training (Step 3) and wait for success |
| Anomaly suppression not triggering | Heart rate value not far enough above baseline | Increase the test value (e.g., 210 bpm) or lower `ANOMALY_THRESHOLD` in `.env` |
