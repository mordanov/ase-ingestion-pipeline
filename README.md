# Health Intelligence Platform

A production-grade IoT health data ingestion and recommendation platform. Devices (smartwatches, fitness trackers, smartphones) stream telemetry events over HTTP or MQTT; the platform validates, stores, and analyses the data, then serves personalised health recommendations backed by an ML re-ranking and anomaly-detection layer.

---

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Services & Ports](#services--ports)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Database](#database)
- [ML Pipeline](#ml-pipeline)
- [Credits & Rewards](#credits--rewards)
- [Observability](#observability)
- [Development](#development)
- [Testing](#testing)
- [CI/CD](#cicd)
- [Data Storage](#data-storage)

---

## Architecture

```
Devices (HTTP / MQTT)
        │
        ▼
┌───────────────────┐
│   FastAPI App     │  :8000 (internal) / :8100 (external)
│                   │
│  /ingest          │──▶ Validate ──▶ PostgreSQL (telemetry_events)
│  /api/v1/...      │              ──▶ Delta Lake archive
│  /admin/ml/...    │              ──▶ Redis Streams / Kinesis
└───────┬───────────┘              ──▶ Credit engine
        │
        ▼
  Recommendation Providers (Service 1, 2, 3, dynamic)
        │
        ▼
  ML Layer (TFLite re-ranker + Z-score anomaly detector)
        │
        ▼
  RecommendationResponse → device

┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  PostgreSQL  │   │    Redis     │   │  Prometheus  │
│  (state/log) │   │  (embeddings)│   │  + Grafana   │
└──────────────┘   └──────────────┘   └──────────────┘
```

**Key design decisions:**

- **Dual write:** every accepted event is written to PostgreSQL (queryable) *and* Delta Lake (analytical archive).
- **Graceful ML fallback:** if the re-ranker or anomaly detector fails for any reason, the endpoint returns the raw aggregated recommendations without error.
- **Credit economy:** each device earns credits for activity and spends them on recommendations; tiers (bronze → platinum) give multipliers and discounts.
- **Rules engine:** devices can be disabled at runtime; blocked at both ingestion and recommendation time.

---

## Quick Start

**Prerequisites:** Docker, Docker Compose, `make`.

```bash
# 1. Copy and edit environment file
cp .env.example .env
# Set POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, API_KEY at minimum

# 2. Start all services
make dev

# 3. Run database migrations
make migrate

# 4. Seed test devices (optional)
make seed

# 5. Open API docs
open http://localhost:8100/docs
```

The frontend dashboard is at **http://localhost:3200**. Grafana is at **http://localhost:3100** (admin password from `GF_SECURITY_ADMIN_PASSWORD`).

---

## Services & Ports

| Service | External port | Description |
|---|---|---|
| **API** | `8100` | FastAPI application |
| **Frontend** | `3200` | React dashboard (Nginx) |
| **Grafana** | `3100` | Metrics dashboards |
| **Prometheus** | `9090` | Metrics scraping |
| **PostgreSQL** | `5432` | Primary database |
| **Redis** | `6379` | Feature embedding cache |
| **Mosquitto** | `1883` / `8883` | MQTT broker (plain / TLS) |

The API is also available directly at `:8000` inside the Docker network.

---

## API Reference

All endpoints except `/health`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`, and `/ingest` require the header:

```
X-API-Key: <API_KEY>
```

### Health & Metrics

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check → `{"status": "ok"}` |
| `GET` | `/metrics` | Prometheus metrics (no auth) |

### Ingestion

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest` | Ingest one or a batch of telemetry events (202) |

Request body (single event):
```json
{
  "device_id": "watch-abc123",
  "event_id": "evt-001",
  "timestamp": "2026-01-01T12:00:00Z",
  "payload": { "heart_rate": { "bpm": 72 }, "spo2_pct": 98.5 }
}
```

Batch: wrap in `{ "batch_id": "...", "events": [...] }`.

Response includes `credit_results` (credits awarded per device) and `device_disabled_ids` (any devices found to be on the blocklist).

### Devices

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/devices` | List devices (paginated, `?search=`, `?limit=50`, `?offset=0`) |
| `POST` | `/api/v1/devices` | Register a device (201) |
| `GET` | `/api/v1/devices/{id}` | Get device details |
| `GET` | `/api/v1/devices/{id}/credits` | Credit balance + tier info |
| `POST` | `/api/v1/devices/{id}/credits` | Manual credit top-up / adjustment |
| `GET` | `/api/v1/devices/{id}/credits/transactions` | Credit transaction history |
| `GET` | `/api/v1/devices/{id}/events` | Telemetry event history |

### Recommendations

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/devices/{id}/recommendations` | Get personalised recommendations |

Optional body: `{ "min_confidence": 0.2 }`. Costs 1 credit by default (configurable). Returns `402` when balance is zero, `503` when all providers fail. Response includes `personal_relevance_score` (ML re-ranking) and `anomaly_suppressed` flag per item.

### Rules Engine

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/rules/disabled-devices` | List disabled devices |
| `POST` | `/api/v1/rules/disabled-devices` | Disable a device (`{"device_id": "..."}`) |
| `DELETE` | `/api/v1/rules/disabled-devices/{id}` | Re-enable a device (204) |

### ML & Admin

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/ml/retrain` | Trigger full ML training pipeline (202) |
| `GET` | `/admin/ml/training-jobs/{job_id}` | Training job status + metrics |
| `GET` | `/admin/ml/model-package/latest` | Latest on-device model package metadata |
| `GET` | `/admin/ml/model-package/{id}/download` | Download model package ZIP |
| `GET` | `/admin/ml/metrics` | Live ML model quality metrics |

### Configuration & Reporting

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/credit-config` | Active credit configuration |
| `PUT` | `/api/v1/credit-config` | Update credit configuration (creates new version) |
| `GET/POST/PUT/DELETE` | `/api/v1/provider-schemas` | Manage dynamic recommendation providers |
| `GET` | `/api/v1/reports/summary` | Platform health summary (last 24 h) |

---

## Configuration

All settings are read from environment variables (or `.env` file). Copy `.env.example` to get started.

| Variable | Default | Description |
|---|---|---|
| `LOCAL_DEV` | `true` | Use local Redis Streams instead of Kinesis |
| `DATABASE_URL` | — | PostgreSQL async DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `API_KEY` | `dev-key` | Bearer key for all protected endpoints |
| `AWS_REGION` | `eu-central-1` | AWS region (IoT Core, Kinesis) |
| `AWS_IOT_ENDPOINT` | — | IoT Core data endpoint |
| `KINESIS_STREAM_NAME` | `health-platform-events` | Event stream name |
| `SERVICE1_ENDPOINT` | — | Recommendation provider 1 URL |
| `SERVICE2_ENDPOINT` | — | Recommendation provider 2 URL |
| `SERVICE3_ENDPOINT` | _(empty)_ | Optional third provider |
| `RECOMMENDATION_TIMEOUT_SECONDS` | `0.8` | Per-provider timeout |
| `MIN_RECOMMENDATION_SCORE` | `200.0` | Minimum provider confidence score |
| `STALENESS_THRESHOLD_HOURS` | `24` | Events older than this are flagged stale |
| `ANOMALY_THRESHOLD` | `0.5` | Z-score threshold for anomaly detection |
| `MIN_TELEMETRY_DAYS` | `1` | Min days of data for ML inference (raise for prod) |
| `EMBEDDING_TTL_SECONDS` | `300` | Redis feature embedding cache TTL |
| `DELTA_OUTPUT_DIR` | `/data/delta` | Events Delta Lake path |
| `RECOMMENDATIONS_DELTA_DIR` | `/data/recommendations` | Recommendations Delta Lake path |
| `MODEL_ARTIFACT_DIR` | `/data/models` | Trained model artefacts |
| `ON_DEVICE_PACKAGE_DIR` | `/data/packages` | On-device model packages |
| `GF_SECURITY_ADMIN_PASSWORD` | — | Grafana admin password |
| `LOG_LEVEL` | `INFO` | structlog level |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(empty)_ | OpenTelemetry collector URL (optional) |

---

## Database

PostgreSQL 15. Migrations are managed with Alembic.

```bash
make migrate          # apply all pending migrations
make migrate-down     # roll back one migration
```

| Table | Purpose |
|---|---|
| `devices` | Device registry, live credit balance, tier, streak |
| `disabled_devices` | Rules engine blocklist |
| `telemetry_events` | Every accepted ingest event with raw JSONB payload |
| `ingestion_batches` | Batch submission metadata |
| `quarantine_records` | Rejected events with error codes for debugging |
| `recommendation_requests` | Full log of recommendation calls + results |
| `credit_transactions` | Immutable credit ledger |
| `credit_configs` | Versioned credit configuration (earning rules, tiers) |
| `provider_schemas` | Dynamic recommendation provider definitions |
| `ml_training_jobs` | Training run history with quality metrics |
| `ml_trained_models` | Model artefact registry |
| `ml_anomaly_readings` | Per-device Z-score baselines |
| `ml_on_device_packages` | Packaged model bundles for distribution |

---

## ML Pipeline

The ML layer enhances recommendations with two models trained on historical telemetry:

### Re-ranker (TFLite)

A learning-to-rank model that re-orders provider recommendations by personal relevance. Cold-start devices (fewer than `MIN_TELEMETRY_DAYS` days of data) receive the raw aggregated order.

### Anomaly Detector (Z-score)

Compares the latest telemetry reading to the device's historical baseline. Items that would be inappropriate given an abnormal health reading are flagged `anomaly_suppressed: true` in the response.

### Training

```bash
# Trigger via API
curl -X POST http://localhost:8100/admin/ml/retrain \
  -H "X-API-Key: $API_KEY"

# Or use the Recommendations page in the frontend dashboard
```

Training runs asynchronously. Only one job can run at a time (409 if concurrent). Results (NDCG@10, F1) are written to Prometheus on completion and visible in Grafana.

**Prometheus alerts fire when:**
- Model not retrained in > 24 hours (`MLModelStale` — critical)
- Re-ranker NDCG@10 < 0.5 (`MLRerankerNDCGLow`)
- Anomaly detector F1 < 0.5 (`MLAnomalyDetectorF1Low`)
- Inference P99 > 200 ms (`MLInferenceLatencyHigh`)

---

## Credits & Rewards

Every device has a credit balance. Credits are **earned** by sending telemetry and **spent** on recommendation requests.

**Reward tiers** (based on cumulative credits spent): `bronze` → `silver` → `gold` → `platinum`. Higher tiers receive earning multipliers and service cost discounts. Thresholds and multipliers are configurable at runtime via `PUT /api/v1/credit-config`.

**Streak bonuses:** configurable bonuses for 7-day and 30-day activity streaks.

Devices with a zero balance receive `402 Insufficient credits` on recommendation requests.

---

## Observability

### Grafana

Three provisioned dashboards available under the **Platform** folder:

- **health-platform** — ingestion rates, quarantine rate, recommendation latency
- **credits** — per-device credit balances, tier distribution, earning/spending rates
- **ml-monitoring** — model quality scores, inference latency, training staleness

Access at `http://localhost:3100` (or the configured domain).

### Prometheus Alerts

| Alert | Condition | Severity |
|---|---|---|
| `HighRecommendationErrorRate` | > 0.1 errors/s over 5 min | warning |
| `HighIngestQuarantineRate` | > 5% of events quarantined | warning |
| `MLModelStale` | No training in > 24 h | **critical** |
| `MLInferenceLatencyHigh` | P99 > 200 ms | warning |
| `MLRerankerNDCGLow` | NDCG@10 < 0.5 | warning |
| `MLAnomalyDetectorF1Low` | F1 < 0.5 | warning |

### Structured Logging

All application logs use [structlog](https://www.structlog.org/) with JSON output. Every request is tagged with a `trace_id` that propagates through ingestion, validation, publishing, and credit events.

OpenTelemetry traces can be exported by setting `OTEL_EXPORTER_OTLP_ENDPOINT`.

---

## Development

```bash
make dev            # start all Docker services
make stop           # stop all services
make logs           # tail app container logs
make shell          # bash inside app container
make frontend-dev   # Vite dev server at :5173 (hot-reload)
make seed           # register 10 test devices
make lint           # ruff check + format + mypy
make migrate        # run pending Alembic migrations
make compact-delta  # compact + vacuum + checkpoint Delta Lake tables
```

### Pre-commit hooks

Hooks run automatically on every `git commit`:

| Hook | Scope |
|---|---|
| `ruff-format` | Python formatting |
| `ruff` | Python linting + import sorting |
| `prettier` | TypeScript / CSS / JSON formatting |
| `eslint` | TypeScript / React linting |

Install once after cloning:

```bash
pip install pre-commit
pre-commit install
```

---

## Testing

```bash
make test               # all tests
make test-unit          # fast, no external dependencies
make test-integration   # requires Docker services running
make test-contract      # calls live external provider endpoints
make test-frontend      # Vitest (frontend unit tests)
```

| Suite | Files | Notes |
|---|---|---|
| Unit | 17 files | Mocked DB/Redis, no I/O |
| Integration | 14 files | Requires PostgreSQL + Redis |
| Contract | 7 files | Calls real provider endpoints |

Coverage threshold: **80%** (enforced in CI). Migration files are excluded from coverage.

Pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.contract`.

---

## CI/CD

`.github/workflows/ci.yml` — four jobs, all running on `ubuntu-latest`:

```
pre-commit ──┐
             ├──▶ deploy  (push to main only)
test-backend ┤
             │
test-frontend┘
```

- **pre-commit** — ruff + prettier + eslint across the whole repo
- **test-backend** — `pytest tests/unit/` with Python 3.12
- **test-frontend** — Vitest with Node 24
- **deploy** — SSH into EC2, bootstrap Docker/git if needed, pull repo, `docker compose up --build`, wait for health check, run migrations

The deploy job only runs on pushes to `main` (not on pull requests). A `concurrency` guard prevents overlapping deployments.

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_USER` | SSH user (`ubuntu` / `ec2-user`) |
| `EC2_SSH_KEY` | PEM private key contents |
| `GH_TOKEN` | GitHub PAT with `repo` read scope |

The `.env` file must exist at `~/platform/.env` on the instance before the first deploy.

---

## Data Storage

| Data | Where | Retention |
|---|---|---|
| Device state, credits, transactions | **PostgreSQL** | Permanent |
| Accepted telemetry events (archive) | **Delta Lake** (`/data/delta`) | Configurable |
| Recommendation results (archive) | **Delta Lake** (`/data/recommendations`) | Configurable |
| Feature embeddings | **Redis** | 300 s TTL |
| Trained model artefacts | Local filesystem (`/data/models`) | Until replaced |
| On-device model packages | Local filesystem (`/data/packages`) | Until replaced |
| Metrics | **Prometheus** | Default retention |

### Delta Lake Maintenance

A `delta_compactor` sidecar runs every 15 minutes inside Docker. To run manually:

```bash
make compact-delta
# or with custom retention:
python scripts/compact_delta.py \
  --base-dir ./data/delta \
  --recommendations-dir ./data/recommendations \
  --log-retention-hours 24 \
  --dry-run   # preview without writing
```

This performs: file compaction → vacuum → checkpoint → log cleanup.
