# Contract: ML Metrics API

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)  
**Implemented by**: `src/api/routers/ml_metrics.py`

---

## GET /admin/ml/metrics

Returns the four operational monitoring metrics required by FR-018 and User Story 5. Used by the admin ML monitoring dashboard to display live panels.

**Auth**: API key required (`X-API-Key` header).

### Request

```http
GET /admin/ml/metrics
X-API-Key: {api_key}
```

No query parameters.

### Response — 200 OK

```json
{
  "reranker": {
    "model_version": 7,
    "ndcg_at_10": 0.743,
    "deployment_status": "active",
    "deployed_at": "2026-05-05T15:10:00Z"
  },
  "anomaly_detector": {
    "model_version": 7,
    "f1_score": 0.851,
    "deployment_status": "active",
    "deployed_at": "2026-05-05T15:10:00Z"
  },
  "inference": {
    "p99_latency_ms": 18.4,
    "window_seconds": 300
  },
  "staleness": {
    "last_trained_at": "2026-05-05T15:10:00Z",
    "elapsed_seconds": 3720,
    "threshold_seconds": 86400
  }
}
```

#### `reranker` object

| Field | Type | Notes |
|-------|------|-------|
| model_version | int | Sequential version number (A-008) |
| ndcg_at_10 | float \| null | null if no model has been trained yet |
| deployment_status | string | `"active"` \| `"archived"` \| `"failed"` \| `"none"` |
| deployed_at | ISO-8601 \| null | null if no model deployed |

#### `anomaly_detector` object

| Field | Type | Notes |
|-------|------|-------|
| model_version | int | Sequential version number |
| f1_score | float \| null | null if no model has been trained yet |
| deployment_status | string | `"active"` \| `"archived"` \| `"failed"` \| `"none"` |
| deployed_at | ISO-8601 \| null | |

#### `inference` object

| Field | Type | Notes |
|-------|------|-------|
| p99_latency_ms | float | p99 inference latency in milliseconds over the last `window_seconds` |
| window_seconds | int | Rolling window used to compute p99; default 300 s (5 min) |

#### `staleness` object

| Field | Type | Notes |
|-------|------|-------|
| last_trained_at | ISO-8601 \| null | UTC timestamp of last successful training job completion; null if never |
| elapsed_seconds | int \| null | Seconds since `last_trained_at`; null if never trained |
| threshold_seconds | int | Configured staleness alert threshold; default 86400 s (24 h, SC-005) |

### Response — 200 OK (no model trained yet)

```json
{
  "reranker": {
    "model_version": null,
    "ndcg_at_10": null,
    "deployment_status": "none",
    "deployed_at": null
  },
  "anomaly_detector": {
    "model_version": null,
    "f1_score": null,
    "deployment_status": "none",
    "deployed_at": null
  },
  "inference": {
    "p99_latency_ms": null,
    "window_seconds": 300
  },
  "staleness": {
    "last_trained_at": null,
    "elapsed_seconds": null,
    "threshold_seconds": 86400
  }
}
```

### Response — 401 Unauthorized

```json
{ "detail": "Invalid or missing API key" }
```

---

## Prometheus Metrics

The same four values are also exposed as Prometheus Gauges on the existing `/metrics` endpoint (FR-018, Constitution VI). Metric names:

| Prometheus metric | Matches API field |
|-------------------|------------------|
| `ml_reranker_ndcg_at_10` | `reranker.ndcg_at_10` |
| `ml_anomaly_detector_f1_score` | `anomaly_detector.f1_score` |
| `ml_inference_p99_latency_ms` | `inference.p99_latency_ms` |
| `ml_model_staleness_seconds` | `staleness.elapsed_seconds` |

---

## Acceptance Criteria (from spec)

- After a completed training cycle, all four fields in the 200 response are non-null (US5 scenario 1, SC-008).
- `staleness.elapsed_seconds` resets (returns to 0 or near-0) within one Prometheus scrape interval after a successful training run (US5 scenario 2).
- `inference.p99_latency_ms` reflects the current sliding window — it does not require a training event to update (US5 scenario 3).
- The endpoint returns 200 with null fields (not 500) when no model has ever been trained.
