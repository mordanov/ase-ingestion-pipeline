# ML Architecture — Health Intelligence Platform

Two lightweight models run at inference time: a **re-ranker** that personalises the order of recommendations and an **anomaly detector** that suppresses inappropriate items when a device's health reading looks unusual. Both are stored as TFLite flatbuffers and trained in a single pipeline run.

---

## Data & Features

**Source data** comes from two Delta Lake tables:
- Telemetry events (`/data/delta`) — each event carries a JSON payload with fields like `heart_rate.bpm`, `steps`, `sleep.hours`.
- Recommendation results (`/data/recommendations`) — per-provider recommendation history used to compute relevance signals.

**Feature engineering** (`FeatureEngineer`) converts each device's raw telemetry into a **64-dimensional float32 vector**:

| Dims | Signal | Derived as |
|------|--------|------------|
| 0–1 | Heart rate | mean, std over all events |
| 2–3 | Step count | mean, std |
| 4–5 | Sleep hours | mean, std |
| 6–63 | — | zero-padded |

Only devices with at least `MIN_TELEMETRY_DAYS` days of data (default 1, raise in prod) contribute meaningful values; the rest remain zero-padded ("cold-start" devices).

---

## Training Pipeline

Triggered via `POST /admin/ml/retrain` or the frontend Recommendations page. Only one job may run at a time (HTTP 409 if concurrent). Progress is written to the `ml_training_jobs` table and queryable via `GET /admin/ml/training-jobs/{id}`.

```
Delta Lake  ──▶  DataExtractor  ──▶  FeatureEngineer  ──▶  ModelTrainer
                 (raw events)        (64-dim vectors         (re-ranker
                                      per device)            + anomaly detector)
                                                                  │
                                                         DbModelRegistry  ──▶  Distributor
                                                         (versions in PG)      (on-device ZIP)
```

### Re-ranker

The re-ranker learns a **global "average user" profile**.

1. Stack all per-device 64-dim vectors into a matrix.
2. Compute the element-wise mean → one 64-dim weight vector.
3. Persist this vector as a TFLite `FULLY_CONNECTED` layer (no bias, no activation) at `/data/models/reranker_<job_id>.tflite`.

Evaluation metric: **NDCG@10** — devices are ranked by `telemetry_days` (proxy for engagement); `sample_count` is used as the relevance label. Written to Prometheus gauge `ml_reranker_ndcg_at_10`.

### Anomaly Detector

The anomaly detector learns the **typical range of each feature dimension**.

1. Compute the standard deviation per dimension across all device vectors.
2. Store `1 / std` as a TFLite `FULLY_CONNECTED` weight vector (Z-score normalisation weights) at `/data/models/anomaly_<job_id>.tflite`.

Evaluation metric: **F1 score** — ground truth label is `sample_count ≥ threshold`; predicted label is `telemetry_days ≥ 14`. Written to Prometheus gauge `ml_anomaly_f1_score`.

---

## Inference — Per Recommendation Request

```
GET /api/v1/devices/{id}/recommendations
        │
        ├─ Aggregate raw items from providers (Service 1, 2, 3)
        │
        ├─ Re-ranker
        │     ├─ Cold-start? (telemetry_days < MIN_TELEMETRY_DAYS)  ──▶ skip, keep original order
        │     ├─ Retrieve 64-dim device embedding from Redis (300 s TTL)
        │     ├─ Derive item feature vector from recommendation text (SHA-256 hash → 64 floats)
        │     ├─ Score = sigmoid(device_vector · item_vector)  [dot product via FULLY_CONNECTED]
        │     └─ Sort items by score descending
        │
        ├─ Anomaly Detector
        │     ├─ Load last 200 AnomalyReading rows from PostgreSQL (device baseline)
        │     ├─ No baseline? ──▶ skip suppression
        │     ├─ Z-score = |( reading_value − baseline_mean ) / baseline_std|
        │     ├─ Anomaly score = sigmoid(max_z − 2.0)   (~0.5 at 2σ, ~0.88 at 4σ)
        │     └─ Score > threshold (default 0.5) → suppress activity-intensifying items
        │           (keywords: "exercise", "run", "workout", "intense", "vigorous", "high-intensity")
        │           Guarantee: at least 1 item always returned
        │
        └─ Return RecommendationResponse
              • personal_relevance_score  — re-ranker score (null for cold-start)
              • anomaly_suppressed        — true if the anomaly detector flagged this item
```

---

## Cold-Start Handling

A device is "cold-start" until it has `MIN_TELEMETRY_DAYS` days of recorded telemetry. During cold-start:
- The re-ranker returns items in the original aggregated order (no personalisation).
- `personal_relevance_score` is `null` in the response.
- The anomaly detector still runs if a baseline exists in `ml_anomaly_readings`.

---

## Feature Embedding Cache (Redis)

Computing 64-dim embeddings from raw telemetry on every request would be expensive. Instead:
- `RedisFeatureStore` caches each device's embedding as a hex-encoded string in Redis with a 300-second TTL.
- A background coroutine refreshes embeddings every 150 s so that the cache is warm before TTL expiry.
- If Redis is unavailable, inference falls back to a cold-start path gracefully.

---

## Model Versioning & Rollback

`DbModelRegistry` stores every trained model artefact in the `ml_trained_models` PostgreSQL table. On each successful training run:
1. The new model is inserted as `is_active = true`.
2. The previous active model is archived (`is_active = false`).
3. Rollback to the predecessor is supported by the registry API.

The latest model package (TFLite files + metadata) can be downloaded via `GET /admin/ml/model-package/latest/download` for deployment to edge devices.

---

## Observability

| Prometheus metric | What it tracks |
|---|---|
| `ml_reranker_ndcg_at_10` | Re-ranker quality; alert fires below 0.5 |
| `ml_anomaly_f1_score` | Anomaly detector quality; alert fires below 0.5 |
| `ml_model_staleness_seconds` | Seconds since last successful training; critical alert at > 24 h |
| `ml_inference_p99_latency_ms` | Tail inference latency; alert fires above 200 ms |
| `ml_inference_outcome_total` | Labelled `scored` / `cold_start` / `fallback` |
| `ml_anomaly_requests_evaluated_total` | Requests where anomaly baseline existed |
| `ml_anomaly_suppressed_items_total` | Items suppressed across all requests |

All metrics are visible in Grafana under **Platform → ml-monitoring**.

---

## Limitations & Next Steps

| Area | Current state | Possible improvement |
|---|---|---|
| Re-ranker model | Global mean vector (single shared profile) | Per-device collaborative filter or neural re-ranker |
| Item features | SHA-256 hash of recommendation text → random-looking floats | Semantic embeddings (e.g. sentence-transformers) |
| Training data | Telemetry volume only; no explicit click/accept signal | Collect accept/dismiss events for supervised ranking |
| Anomaly baseline | Last 200 readings from PG (`ml_anomaly_readings`) | Sliding window with exponential decay |
| Cold-start threshold | Fixed `MIN_TELEMETRY_DAYS` (default 1) | Adaptive threshold based on data quality |
