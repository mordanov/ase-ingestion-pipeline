# Data Model: ML Recommendation System

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-05-05

## Entities

### UserEmbedding

Cached per-user behavioural feature vector. Stored in Redis (not PostgreSQL) because it is ephemeral and latency-critical; the TTL enforces freshness automatically (A-003).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| device_id | UUID | key, FK → Device | Identifies the user/device |
| vector | bytes | NOT NULL | Serialised float32 array; dimension fixed per model version |
| model_version | int | NOT NULL | Which TrainedModel produced this vector |
| computed_at | datetime (UTC) | NOT NULL | Used to detect stale embeddings after model updates |
| ttl_seconds | int | DEFAULT 300 | Redis TTL; 5-minute default (A-003) |

**Redis key format**: `ml:embedding:{device_id}`  
**Validation**: Vector byte length MUST equal `model_input_dim × 4` (float32). Mismatch triggers async recomputation and cache miss fallback.  
**Expiry behaviour**: On TTL expiry, the next inference request for this user gets a cache miss, falls back to raw ordering, and triggers async recomputation (spec edge case: "user embedding cannot be retrieved in time").

---

### RecommendationItem (extension of existing)

Extends the existing `RecommendationItem` returned by the recommendation aggregator with two new ML-layer fields.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| personal_relevance_score | float \| null | NULLABLE; range [0.0, 1.0] | NULL on cold-start (FR-003) or ML unavailable (FR-004) |
| anomaly_suppressed | bool | NOT NULL; DEFAULT false | True when anomaly score exceeds suppression threshold (FR-006) |

**State transitions**:

| User state | personal_relevance_score | anomaly_suppressed |
|------------|--------------------------|-------------------|
| Cold-start (< 7 days history) | NULL | false |
| Warm user, no anomaly | [0.0, 1.0] | false |
| Warm user, anomaly detected, activity-intensification item | [0.0, 1.0] | true |
| All items suppressed — at-least-one guarantee applied | — | false on exactly one retained item (FR-007) |

**At-least-one guarantee (FR-007)**: If anomaly suppression would produce an empty list, the lowest-risk item (lowest activity-intensification score) is retained with `anomaly_suppressed = false`. All other suppressed items are excluded from the response.

---

### AnomalyReading

Persisted record of each anomaly detection evaluation. Stored in PostgreSQL for audit, baseline computation, and dashboard queries.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK, auto-generated | |
| device_id | UUID | NOT NULL; FK → devices | |
| reading_timestamp | datetime (UTC) | NOT NULL | Timestamp of the evaluated telemetry event |
| anomaly_score | float | NOT NULL; range [0.0, 1.0] | Output of the anomaly detector model |
| threshold_exceeded | bool | NOT NULL | True if anomaly_score > suppression_threshold at evaluation time |
| evaluated_fields | JSONB | NOT NULL | Map of field name → observed value (e.g., `{"heart_rate": 142, "steps": 200}`) |
| suppression_threshold | float | NOT NULL | Threshold value in effect at evaluation time (default 0.5, A-005) |
| created_at | datetime (UTC) | NOT NULL; DEFAULT now() | DB record creation time |

**Index**: `(device_id, reading_timestamp DESC)` — used by the baseline computation query that scans recent readings to compute per-user rolling mean/std.  
**PII annotation**: `evaluated_fields` contains physiological readings. Covered by existing HIPAA/GDPR data handling policy (Constitution V).  
**Retention**: Subject to the platform-wide data retention policy; no ML-specific retention rule.

---

### TrainedModel

Versioned model artifact record. Stored in PostgreSQL. Both the re-ranker and anomaly detector produce one row each per training run.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | int | PK, sequential | |
| model_type | enum | NOT NULL; values: `reranker`, `anomaly_detector` | |
| version | int | NOT NULL; UNIQUE per model_type | Sequential integer (A-008) |
| training_job_id | UUID | NOT NULL; FK → ml_training_jobs | |
| artifact_path | str | NOT NULL | Path to `.tflite` file in object store or local volume |
| predecessor_version | int | NULLABLE; FK → ml_trained_models.id | Points to the model this version supersedes; used for rollback (FR-020) |
| ndcg_at_10 | float | NULLABLE | Populated for `reranker` models only |
| f1_score | float | NULLABLE | Populated for `anomaly_detector` models only |
| deployment_status | enum | NOT NULL; values: `active`, `archived`, `failed` | |
| trained_at | datetime (UTC) | NOT NULL | |
| deployed_at | datetime (UTC) | NULLABLE | Set when status transitions to `active` |

**Constraint**: At most one row with `deployment_status = 'active'` per `model_type`. Enforced by a partial unique index.  
**State transitions**:
- `active` → `archived`: when a newer version is activated (normal promotion)
- `archived` → `active`: rollback operation (FR-020); the previously active version is simultaneously set to `archived`
- Any → `failed`: training evaluation below threshold; terminal state

---

### OnDeviceModelPackage

Distribution-ready ZIP artifact containing both active TFLite models. Created by the `Distributor` component after a successful training run.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK, auto-generated | |
| reranker_model_id | int | NOT NULL; FK → ml_trained_models | Must have deployment_status = 'active' |
| anomaly_detector_model_id | int | NOT NULL; FK → ml_trained_models | Must have deployment_status = 'active' |
| package_path | str | NOT NULL | Path to `.zip` file in object store or local volume |
| compatibility_metadata | JSONB | NOT NULL | e.g., `{"min_tflite_version": "2.13", "reranker_input_dim": 64, "anomaly_input_dim": 16}` |
| created_at | datetime (UTC) | NOT NULL | |
| distributed_count | int | NOT NULL; DEFAULT 0 | Incremented on each device sync distribution event |

**Package contents (ZIP)**:
```
ml_package_v{reranker_v}_{anomaly_v}.zip
├── reranker.tflite
├── anomaly_detector.tflite
└── manifest.json            # version IDs, created_at, compatibility_metadata
```

---

### TrainingJob

Record of a single training pipeline execution. Stored in PostgreSQL. Provides the status tracking needed by the admin UI (FR-015) and the audit log (FR-019).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK, auto-generated | |
| status | enum | NOT NULL; values: `running`, `succeeded`, `failed` | |
| triggered_by | str | NOT NULL | Admin user identifier or `system` |
| started_at | datetime (UTC) | NOT NULL | |
| ended_at | datetime (UTC) | NULLABLE | NULL while running |
| error_message | str | NULLABLE | Populated on `failed`; includes pipeline step and root cause |
| reranker_model_id | int | NULLABLE; FK → ml_trained_models | Populated on `succeeded` |
| anomaly_detector_model_id | int | NULLABLE; FK → ml_trained_models | Populated on `succeeded` |
| reranker_ndcg_at_10 | float | NULLABLE | Evaluation result, copied from TrainedModel on `succeeded` |
| anomaly_detector_f1 | float | NULLABLE | Evaluation result, copied from TrainedModel on `succeeded` |

**Constraint**: At most one row with `status = 'running'`. Enforced at application layer check (FR-016) backed by a partial unique index on `(status)` where `status = 'running'`.  
**Lifecycle**: `running` → `succeeded` (terminal) or `running` → `failed` (terminal). No re-run of a failed job; a new job must be triggered.  
**Logging**: All transitions logged as structured JSON with correlation ID (Constitution VI, FR-019).

---

## Relationships

```
Device (existing)
  ├── 1:N  AnomalyReading          (device_id → devices.id)
  └── 1:1  UserEmbedding (Redis)   (key: ml:embedding:{device_id})

TrainingJob
  └── 1:2  TrainedModel            (reranker_model_id, anomaly_detector_model_id)

TrainedModel
  └── 1:1  TrainedModel (self)     (predecessor_version, for rollback chain)

TrainedModel (reranker, active) ──┐
                                   ├── N:1  OnDeviceModelPackage
TrainedModel (anomaly, active)  ──┘

RecommendationItem (in-memory, not persisted)
  └── augmented with personal_relevance_score + anomaly_suppressed per ML inference
```

---

## Database Migration

**File**: `src/db/migrations/versions/005_ml_tables.py`

Creates the following tables:
- `ml_training_jobs`
- `ml_trained_models`
- `ml_anomaly_readings`
- `ml_on_device_packages`

Partial unique indexes:
- `ix_ml_training_jobs_one_running` on `ml_training_jobs` where `status = 'running'` (ensures at most one concurrent job, FR-016)
- `ix_ml_trained_models_active_reranker` on `(model_type, deployment_status)` where `model_type = 'reranker' AND deployment_status = 'active'`
- `ix_ml_trained_models_active_anomaly` on `(model_type, deployment_status)` where `model_type = 'anomaly_detector' AND deployment_status = 'active'`

No foreign-key cascades on deletion; all ML records are append-only for audit purposes (Constitution V, FR-019).
