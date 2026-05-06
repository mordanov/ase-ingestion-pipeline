# Full Data Flow — Ingestion to Model

This document traces a single telemetry event from the moment a device sends it, through storage and credit accounting, all the way to its contribution to the trained ML models that personalise recommendations for that device.

---

## Overview

```
Device (HTTP / MQTT)
        │
        ▼
  [1] Parse & validate
        │ rejected ──▶ quarantine_records (PostgreSQL)
        │
        ▼
  [2] Dual write
        ├──▶ telemetry_events (PostgreSQL)       — queryable state
        └──▶ Delta Lake /data/delta              — analytical archive
        │
        ▼
  [3] Credit award
        └──▶ credit_transactions + devices.credit_balance (PostgreSQL)
        │
        ▼
  [4] Stream publish
        └──▶ Redis Streams (local) / Kinesis (prod)
        │
        ▼
  [5] ML training (triggered manually or via API)
        ├── DataExtractor   reads Delta Lake
        ├── FeatureEngineer builds 64-dim vectors per device
        ├── ModelTrainer    trains re-ranker + anomaly detector
        └── DbModelRegistry saves .tflite artefacts to PostgreSQL
        │
        ▼
  [6] Inference
        └── re-ranker + anomaly detector applied on next recommendation request
```

---

## Step 1 — Parse & Validate

**Entry points:**
- HTTP: `POST /ingest` — single event or `{ "batch_id": "...", "events": [...] }`
- MQTT: Mosquitto broker on `:1883` / `:8883` → stream consumer → same validation path

**Parsing** (`HttpIngestionAdapter`) extracts `device_id`, `event_id`, `timestamp`, and `payload` from the raw JSON. A parse failure immediately returns 202 with `quarantined: 1`.

**Validation** (`validate_event`) runs four checks in order:

| Check | Fail result |
|---|---|
| `device_id` present | raise `MISSING` |
| `event_id` present | raise `MISSING` |
| Device registered in `devices` table | `UNKNOWN_DEVICE` → quarantine |
| Device on `disabled_devices` blocklist | `DEVICE_DISABLED` → quarantine + added to `device_disabled_ids` in response |

Passing events are flagged:
- **`is_stale`**: `event_timestamp` older than `STALENESS_THRESHOLD_HOURS` (default 24 h). Stale events are still accepted — they get `validation_status = stale` in the DB.
- **`is_anomaly`**: set if the payload contains `"is_anomaly": true` from the device itself.

Duplicate `event_id` values are silently skipped (idempotent ingest).

---

## Step 2 — Dual Write

Every accepted event is written to two stores in the same request:

### PostgreSQL — `telemetry_events`

Row written per event:

| Column | Value |
|---|---|
| `device_id` | FK to `devices` |
| `event_id` | provider-assigned, unique |
| `source_protocol` | `http` or `mqtt` |
| `event_timestamp` | device-reported time |
| `is_stale` | from validator |
| `is_anomaly` | from validator / payload |
| `validation_status` | `valid` or `stale` |
| `payload` | full JSONB payload |
| `trace_id` | request-scoped UUID for log correlation |

### Delta Lake — `/data/delta`

The same event is appended to a Parquet-backed Delta Lake table via `DeltaEventWriter`. Columns include `device_id`, `event_timestamp`, `payload_json` (serialised), `is_stale`, `trace_id`.

The Delta Lake copy is what the **ML training pipeline reads** — it is optimised for bulk scans across all devices, whereas PostgreSQL is optimised for single-device lookups. A `delta_compactor` sidecar compacts, vacuums, and checkpoints the table every 15 minutes.

---

## Step 3 — Credit Award

After writing the event, `EarningService.award_for_event()` credits the device:

1. Reads the active `CreditConfig` from PostgreSQL (earning rates, tier multipliers, streak bonuses).
2. Computes `activity_reward` based on payload fields (step count, activity level) × tier multiplier.
3. Updates `devices.credit_balance` and appends a row to `credit_transactions` (immutable ledger).
4. Returns the awarded amount in `credit_results` in the ingest response — the simulator and device can read this.

---

## Step 4 — Stream Publish

The validated event is also pushed to a message stream for downstream consumers (e.g. digital twin sync, future real-time analytics):

- **Local dev** (`LOCAL_DEV=true`): Redis Streams (`health-platform-events` key)
- **Production**: AWS Kinesis Data Streams

Publish failures are logged as warnings and do not affect the 202 response — the event is already persisted in PostgreSQL and Delta Lake.

---

## Step 5 — ML Training

Training is triggered manually (`POST /admin/ml/retrain`) or from the frontend Recommendations page. The pipeline runs asynchronously; only one job can run at a time.

### 5a — Data Extraction (`DataExtractor`)

Reads **all** telemetry from the Delta Lake archive (`/data/delta`) into memory as `TelemetryRecord` objects:

```
device_id | event_timestamp | heart_rate | steps | sleep_duration | activity_level
```

Payload fields extracted: `payload.heart_rate.bpm`, `payload.steps.count`, `payload.sleep.duration_minutes`.

### 5b — Feature Engineering (`FeatureEngineer`)

Groups records by `device_id`. Devices with fewer than `MIN_TELEMETRY_DAYS` calendar days of data are excluded.

For each eligible device, a **64-dimensional float32 vector** is built:

| Dims | Signal | Derived as |
|---|---|---|
| 0 | Heart rate mean | `mean(bpm) / 200.0` |
| 1 | Heart rate std | `std(bpm) / 50.0` |
| 2 | Steps mean | `mean(steps) / 200.0` |
| 3 | Steps std | `std(steps) / 50.0` |
| 4 | Sleep mean | `mean(duration_minutes) / 200.0` |
| 5 | Sleep std | `std(duration_minutes) / 50.0` |
| 6–63 | — | zero-padded |

The vector is struct-packed as raw `float32` bytes and stored in a `DeviceFeatures` object alongside `telemetry_days` (distinct calendar days) and `sample_count` (total events).

### 5c — Model Training (`ModelTrainer`)

Both models are trained in the same call from the same set of device vectors.

**Re-ranker:**
1. Stack all device vectors into a matrix.
2. Compute the element-wise mean → one 64-dim "global average user" weight vector.
3. Persist as TFLite `FULLY_CONNECTED` flatbuffer: `weights = global_mean`, no bias, no activation.
4. NDCG@10 is computed (devices ranked by `telemetry_days`, labels = `sample_count`) and stored in the artifact.

**Anomaly detector:**
1. Compute per-dimension standard deviation across all device vectors.
2. `weights = 1 / std` per dimension (Z-score normalisation factors).
3. Persist as TFLite `FULLY_CONNECTED` flatbuffer.
4. F1 score computed (`sample_count ≥ threshold` as ground truth, `telemetry_days ≥ 14` as predicted) and stored.

Both artefacts saved to `/data/models/reranker_<job_id>.tflite` and `/data/models/anomaly_<job_id>.tflite`.

### 5d — Registry & Packaging (`DbModelRegistry`, `Distributor`)

Each trained model is registered in the `ml_trained_models` PostgreSQL table. The previous active model is archived. The job record in `ml_training_jobs` is updated to `succeeded` with NDCG and F1 scores.

Prometheus gauges `ml_reranker_ndcg_at_10`, `ml_anomaly_f1_score`, and `ml_model_staleness_seconds` are updated immediately after training.

If `package_dir` is configured, `Distributor` builds a ZIP bundle (TFLite files + metadata JSON) written to `/data/packages` — downloadable via `GET /admin/ml/model-package/latest/download`.

---

## Step 6 — Inference (next recommendation request)

When the device calls `POST /api/v1/devices/{id}/recommendations`:

1. Provider APIs are called in parallel; results are aggregated and deduplicated (see `recommendation-aggregation.md`).
2. **Re-ranker** retrieves the device's embedding from Redis (refreshed from Delta Lake every 150 s, 300 s TTL). For each recommendation item, it computes a dot-product score against a hash-derived item vector. Items are re-sorted by score. Cold-start devices (< `MIN_TELEMETRY_DAYS`) skip this step.
3. **Anomaly detector** loads the last 200 `ml_anomaly_readings` rows from PostgreSQL, computes per-feature mean/std baseline, Z-scores the latest telemetry payload, and suppresses activity-intensifying items if the max Z-score exceeds the threshold (default 0.5). At least one item always passes through.
4. The final list — personalised order, anomaly flags, `personal_relevance_score` per item — is returned to the device.

---

## What Each Device's Events Actually Drive

| Data written at ingest | Used by ML how |
|---|---|
| `payload.heart_rate.bpm` | Re-ranker feature dims 0–1; anomaly baseline dims 0–1 |
| `payload.steps.count` | Re-ranker feature dims 2–3; anomaly baseline dims 2–3 |
| `payload.sleep.duration_minutes` | Re-ranker feature dims 4–5; anomaly baseline dims 4–5 |
| `event_timestamp` (distinct days) | Cold-start gate: device excluded until ≥ `MIN_TELEMETRY_DAYS` distinct days |
| Total event count | `sample_count` used as relevance label for NDCG evaluation |

The more events a device sends, the more stable its feature vector becomes, which improves re-ranking personalisation and tightens the anomaly baseline.
