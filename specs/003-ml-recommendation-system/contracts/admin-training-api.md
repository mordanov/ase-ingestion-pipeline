# Contract: Admin Training API

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)  
**Implemented by**: `src/api/routers/ml_training.py`

---

## POST /admin/ml/retrain

Initiates the full ML training pipeline (re-ranker + anomaly detector in a single run, FR-014). Returns immediately with the newly created `TrainingJob` record. The pipeline runs in the background.

**Auth**: API key required (`X-API-Key` header, same as all admin endpoints).

### Request

No request body required.

```http
POST /admin/ml/retrain
X-API-Key: {api_key}
```

### Response — 202 Accepted (job started)

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "triggered_by": "admin",
  "started_at": "2026-05-05T14:23:00Z"
}
```

| Field | Type | Notes |
|-------|------|-------|
| job_id | UUID string | Stable identifier; use with GET /admin/ml/training-jobs/{id} |
| status | string | Always `"running"` on 202 |
| triggered_by | string | Identity of the caller |
| started_at | ISO-8601 datetime | UTC |

### Response — 409 Conflict (training already in progress)

Returned when a job with `status = "running"` already exists (FR-016).

```json
{
  "detail": "Training already in progress",
  "active_job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Response — 401 Unauthorized

```json
{ "detail": "Invalid or missing API key" }
```

---

## GET /admin/ml/training-jobs/{job_id}

Polls the status of a training job. Used by the admin UI to display the progress indicator and completion notification (FR-015).

### Path parameters

| Parameter | Type | Notes |
|-----------|------|-------|
| job_id | UUID string | From the POST /admin/ml/retrain response |

### Response — 200 OK (job in progress)

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "triggered_by": "admin",
  "started_at": "2026-05-05T14:23:00Z",
  "ended_at": null,
  "reranker_ndcg_at_10": null,
  "anomaly_detector_f1": null,
  "error_message": null
}
```

### Response — 200 OK (job succeeded)

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "triggered_by": "admin",
  "started_at": "2026-05-05T14:23:00Z",
  "ended_at": "2026-05-05T15:10:00Z",
  "reranker_ndcg_at_10": 0.743,
  "anomaly_detector_f1": 0.851,
  "error_message": null
}
```

### Response — 200 OK (job failed)

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "triggered_by": "admin",
  "started_at": "2026-05-05T14:23:00Z",
  "ended_at": "2026-05-05T14:31:00Z",
  "reranker_ndcg_at_10": null,
  "anomaly_detector_f1": null,
  "error_message": "Feature engineering step failed: insufficient training data (< 100 users with 7+ days history)"
}
```

| Field | Type | Notes |
|-------|------|-------|
| status | string | `"running"` \| `"succeeded"` \| `"failed"` |
| ended_at | ISO-8601 \| null | null while running |
| reranker_ndcg_at_10 | float \| null | null until succeeded |
| anomaly_detector_f1 | float \| null | null until succeeded |
| error_message | string \| null | null unless failed |

### Response — 404 Not Found

```json
{ "detail": "Training job not found" }
```

---

## Acceptance Criteria (from spec)

- Starting a job while one is running returns 409 with a clear message — no duplicate job created (FR-016, US4 scenario 2).
- A failed job leaves the previously active model unchanged (US4 scenario 3).
- A succeeded job response includes both `reranker_ndcg_at_10` and `anomaly_detector_f1` (US4 scenario 1).
- The admin can reach "job started" via one POST and observe results via GET polling, completing the retrain workflow in under 5 minutes of active interaction (SC-006).
