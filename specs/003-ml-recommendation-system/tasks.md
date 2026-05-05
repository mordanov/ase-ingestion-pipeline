# Tasks: ML Recommendation System

**Input**: Design documents from `/specs/003-ml-recommendation-system/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Included — TDD is NON-NEGOTIABLE per constitution (Principle II). Write each test task first, confirm it fails, then implement.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- TDD order within each story: failing tests → models → services → API → integration

---

## Phase 1: Setup

**Purpose**: Add ML dependencies, directory structure, and configuration so all subsequent phases can start.

- [X] T001 Add ML dependencies to pyproject.toml: `tensorflow>=2.13`, `tflite-runtime>=2.13`, `scikit-learn>=1.4`
- [X] T002 Create `src/ml/` directory structure per plan.md: `__init__.py`, `training/` sub-package
- [X] T003 [P] Add ML config fields to `src/config.py`: `anomaly_threshold: float = 0.5`, `model_artifact_dir: str = "/data/models"`, `on_device_package_dir: str = "/data/packages"`, `embedding_ttl_seconds: int = 300`
- [X] T004 [P] Create test directory structure: `tests/unit/ml/training/`, `tests/integration/ml/`, `tests/contract/ml/` with `__init__.py` files
- [X] T005 [P] Add `model_artifact_dir` and `on_device_package_dir` volumes to `docker-compose.yml` and `Makefile` `dev` target (`mkdir -p`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Abstract interfaces, ORM models, and DB migration that ALL user story phases depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 Define abstract interfaces in `src/ml/interfaces.py`: `Reranker` (abstract `rerank` method), `AnomalyDetector` (abstract `detect` method), `FeatureStore` (abstract `get_embedding` / `set_embedding`), `ModelRegistry` (abstract `get_active_model` / `register_model`)
- [X] T007 [P] Create `TrainingJob` SQLAlchemy ORM model in `src/db/models/ml_training_job.py` (fields: id UUID, status enum, triggered_by, started_at, ended_at, error_message, reranker_model_id FK, anomaly_detector_model_id FK, reranker_ndcg_at_10, anomaly_detector_f1)
- [X] T008 [P] Create `TrainedModel` SQLAlchemy ORM model in `src/db/models/ml_trained_model.py` (fields: id int PK, model_type enum, version int, training_job_id FK, artifact_path, predecessor_version FK self, ndcg_at_10, f1_score, deployment_status enum, trained_at, deployed_at)
- [X] T009 [P] Create `AnomalyReading` SQLAlchemy ORM model in `src/db/models/ml_anomaly_reading.py` (fields: id UUID, device_id FK, reading_timestamp, anomaly_score float, threshold_exceeded bool, evaluated_fields JSONB, suppression_threshold float, created_at)
- [X] T010 [P] Create `OnDeviceModelPackage` SQLAlchemy ORM model in `src/db/models/ml_on_device_package.py` (fields: id UUID, reranker_model_id FK, anomaly_detector_model_id FK, package_path, compatibility_metadata JSONB, created_at, distributed_count int)
- [X] T011 Write Alembic migration `src/db/migrations/versions/005_ml_tables.py` creating all 4 ML tables with partial unique indexes (one running job, one active model per type) — depends on T007–T010
- [X] T012 Extend `RecommendationItem` in `src/recommendation/interfaces.py` with `personal_relevance_score: float | None` and `anomaly_suppressed: bool = False` fields

**Checkpoint**: Foundation ready — all user story phases can now begin in parallel.

---

## Phase 3: User Story 1 — Personalised Recommendation Delivery (Priority: P1) 🎯 MVP

**Goal**: Users with ≥ 7 days of telemetry history receive re-ranked recommendations with personal relevance scores. Cold-start and ML-unavailable paths fall back gracefully.

**Independent Test**: Submit a recommendation request for a device with 7+ days of seeded telemetry. Verify the response contains all provider items in a different order with non-null `personal_relevance_score` on each item. Submit for a new device and verify `personal_relevance_score` is `null` and response time is normal.

### Tests for User Story 1 (write first — confirm they FAIL before implementing)

- [X] T013 [P] [US1] Write failing unit tests for `FeatureStore` in `tests/unit/ml/test_feature_store.py`: Redis read/write, TTL enforcement, cache miss returns None, serialisation round-trip for float32 vectors
- [X] T014 [P] [US1] Write failing unit tests for `Reranker` in `tests/unit/ml/test_reranker.py`: warm-user path attaches scores and re-orders, cold-start (< 7 days) returns raw order with null scores, ML-unavailable exception triggers raw-order fallback
- [X] T015 [P] [US1] Write failing integration test for personalised recommendations in `tests/integration/ml/test_ml_api.py`: warm device gets non-null scores; new device gets null scores; no errors on either path

### Implementation for User Story 1

- [X] T016 [P] [US1] Implement `RedisFeatureStore` in `src/ml/feature_store.py`: `get_embedding(device_id)` returns `UserEmbedding | None`, `set_embedding(device_id, vector, model_version)` with TTL from config — make T013 pass
- [X] T017 [US1] Implement `TFLiteReranker` in `src/ml/reranker.py`: load `.tflite` artifact from `ModelRegistry`, run item-tower inference per candidate, attach `personal_relevance_score`, detect cold-start (< 7 days) and return raw order with null scores, catch exceptions and fall back to raw order — make T014 pass (depends on T006, T008, T016)
- [X] T018 [US1] Integrate `Reranker` into `src/recommendation/aggregator.py` via constructor injection: call `reranker.rerank(device_id, items)` after provider aggregation, merge scores into response — make T015 pass (depends on T017)
- [X] T019 [US1] Register `RedisFeatureStore` and `TFLiteReranker` in `src/api/dependencies.py` DI factory (depends on T018)

**Checkpoint**: User Story 1 fully functional. A warm device receives re-ranked recommendations with scores; a cold-start device receives valid raw-ordered recommendations without error.

---

## Phase 4: User Story 2 — Anomaly-Aware Recommendation Adjustment (Priority: P2)

**Goal**: Telemetry readings that deviate from a user's personal baseline raise an anomaly flag that suppresses activity-intensification recommendations. The system always returns at least one recommendation. Users with < 7 days baseline receive no flags.

**Independent Test**: Send a telemetry payload with heart rate well above the device's established baseline. Request recommendations and verify activity-intensification items have `anomaly_suppressed: true` or are absent. Verify that at least one recommendation is always returned regardless of suppression.

### Tests for User Story 2 (write first — confirm they FAIL)

- [X] T020 [P] [US2] Write failing unit tests for `AnomalyDetector` in `tests/unit/ml/test_anomaly_detector.py`: within-baseline reading produces score < threshold; significantly elevated reading produces score > threshold; new user (no baseline) produces no flag; all items suppressed triggers at-least-one guarantee
- [X] T021 [P] [US2] Write failing integration test for anomaly-suppressed recommendations in `tests/integration/ml/test_anomaly_api.py`: anomalous ingest followed by recommendations request produces suppressed items; at-least-one item always returned

### Implementation for User Story 2

- [X] T022 [P] [US2] Implement `TFLiteAnomalyDetector` in `src/ml/anomaly_detector.py`: Z-score baseline from rolling window, sigmoid output mapped to [0, 1] score, suppression threshold from config (A-005), no-flag-for-new-user logic (< 7 days, FR-008), at-least-one guarantee (FR-007) — make T020 pass (depends on T006, T009)
- [X] T023 [US2] Persist `AnomalyReading` after each detection in `src/ml/anomaly_detector.py` using async SQLAlchemy session (depends on T022, T009)
- [X] T024 [US2] Wire `AnomalyDetector` into `src/recommendation/aggregator.py` via constructor injection: evaluate anomaly score before final list assembly, apply suppression, enforce at-least-one — make T021 pass (depends on T022, T018)
- [X] T025 [US2] Register `TFLiteAnomalyDetector` in `src/api/dependencies.py` DI factory (depends on T024)

**Checkpoint**: User Stories 1 and 2 both functional. Warm users see re-ranked, anomaly-filtered recommendations; cold-start and no-baseline paths are safe.

---

## Phase 5: User Story 3 — Offline On-Device Recommendations (Priority: P3)

**Goal**: After a successful training run, a ZIP model package is built and made available for download via the device sync endpoint. Devices use the manifest to verify compatibility and fall back to the prior model if incompatible.

**Independent Test**: After a seeded training run, call `GET /admin/ml/model-package/latest` and verify it returns a non-null `download_url`. Download the ZIP, unzip, and confirm `manifest.json` contains both model version numbers and `min_tflite_runtime_version`.

### Tests for User Story 3 (write first — confirm they FAIL)

- [X] T026 [P] [US3] Write failing unit tests for `Distributor` in `tests/unit/ml/test_distributor.py`: ZIP contains both `.tflite` files and `manifest.json`; manifest fields match the input TrainedModel versions; compatibility metadata is populated
- [X] T027 [P] [US3] Write failing contract tests for model distribution endpoints in `tests/contract/ml/test_admin_api_contracts.py`: `GET /admin/ml/model-package/latest` returns correct schema; 404 when no package exists; download endpoint returns `application/zip`

### Implementation for User Story 3

- [X] T028 [P] [US3] Implement `Distributor` in `src/ml/distributor.py`: assemble ZIP from active re-ranker and anomaly-detector TFLite artifacts, generate `manifest.json`, persist `OnDeviceModelPackage` record — make T026 pass (depends on T006, T010)
- [X] T029 [US3] Add model distribution API endpoints to `src/api/routers/ml_training.py`: `GET /admin/ml/model-package/latest` and `GET /admin/ml/model-package/{package_id}/download` — make T027 pass (depends on T028)
- [X] T030 [US3] Register distribution routes in `src/api/main.py` (depends on T029)

**Checkpoint**: Model packages can be built and downloaded. The device sync infrastructure can begin integrating against the distribution endpoint.

---

## Phase 6: User Story 4 — Admin-Triggered Model Retraining (Priority: P4)

**Goal**: An admin clicks "Retrain Models", a background pipeline runs both models through extract→engineer→train→evaluate→register, and the admin receives a completion notification with NDCG@10 and F1 values. Concurrent retrain attempts are rejected.

**Independent Test**: `POST /admin/ml/retrain` → 202 with `job_id`. Poll `GET /admin/ml/training-jobs/{job_id}` until `"succeeded"`. Verify response includes non-null `reranker_ndcg_at_10` and `anomaly_detector_f1`. Trigger a second retrain while first is running → 409 "Training already in progress".

### Tests for User Story 4 (write first — confirm they FAIL)

- [X] T031 [P] [US4] Write failing unit tests for `DataExtractor` in `tests/unit/ml/training/test_data_extractor.py`: reads telemetry records from Delta Lake path, reads recommendation records from recommendations archive, handles empty archive gracefully
- [X] T032 [P] [US4] Write failing unit tests for `FeatureEngineer` in `tests/unit/ml/training/test_feature_engineer.py`: produces per-user float32 feature vectors, excludes users with < 7 days history, handles missing telemetry fields with defaults
- [X] T033 [P] [US4] Write failing unit tests for `Evaluator` in `tests/unit/ml/training/test_evaluator.py`: `ndcg_at_10(ranked, relevant)` returns float in [0, 1]; `f1_score(y_true, y_pred)` returns float in [0, 1]; edge cases (empty input, perfect ranking)
- [X] T034 [P] [US4] Write failing contract tests for admin training API in `tests/contract/ml/test_admin_api_contracts.py`: `POST /admin/ml/retrain` → 202 schema; `GET /admin/ml/training-jobs/{id}` → succeeded/failed schema; concurrent retrain → 409 schema
- [X] T035 [US4] Write failing integration test for full training pipeline run in `tests/integration/ml/test_training_pipeline.py`: pipeline reads seeded Delta Lake data, produces both models, job record shows `succeeded`, artifact files exist on disk

### Implementation for User Story 4

- [X] T036 [P] [US4] Implement `DataExtractor` in `src/ml/training/data_extractor.py`: async readers for `delta_output_dir` (telemetry) and `recommendations_delta_dir` (provider responses) using `deltalake` — make T031 pass
- [X] T037 [P] [US4] Implement `FeatureEngineer` in `src/ml/training/feature_engineer.py`: aggregate telemetry events per device, compute rolling mean/std per feature, assemble float32 feature vectors, skip devices with < 7 days history — make T032 pass
- [X] T038 [P] [US4] Implement `Evaluator` in `src/ml/training/evaluator.py`: `ndcg_at_10` using `sklearn.metrics.ndcg_score`, `f1_score` using `sklearn.metrics.f1_score` — make T033 pass
- [X] T039 [US4] Implement `ModelTrainer` in `src/ml/training/model_trainer.py`: TensorFlow two-tower re-ranker training and LSTM autoencoder anomaly detector training, export both to TFLite flatbuffer, save artifact to `model_artifact_dir` (depends on T037)
- [X] T040 [US4] Implement `ModelRegistry` in `src/ml/registry.py`: `register_model`, `get_active_model(model_type)`, `activate_model` (archives previous, sets new to active), `rollback_model` (re-activates predecessor, FR-020) — depends on T008
- [X] T041 [US4] Implement `TrainingPipeline` orchestrator in `src/ml/training/pipeline.py`: ordered steps (extract → engineer → train → evaluate → register), structured job logging (FR-019), marks job succeeded/failed in DB, handles mid-run failure leaving previous model active — make T035 pass (depends on T036, T037, T038, T039, T040)
- [X] T042 [US4] Add structured training job logging to `src/ml/training/pipeline.py`: JSON log entry on each step transition with correlation ID, duration, triggering actor, and resulting metrics (FR-019) — part of T041
- [X] T043 [US4] Implement admin training API router in `src/api/routers/ml_training.py`: `POST /admin/ml/retrain` (start background task, 409 on concurrent run via DB check), `GET /admin/ml/training-jobs/{id}` — make T034 pass (depends on T041)
- [X] T044 [US4] Register training router in `src/api/main.py` (depends on T043)

**Checkpoint**: Admin can trigger retraining via the API and poll for results. Both models are trained, evaluated, and deployed in a single run. Re-running while active returns 409.

---

## Phase 7: User Story 5 — ML Quality Monitoring Dashboard (Priority: P5)

**Goal**: `GET /admin/ml/metrics` returns NDCG@10, F1, p99 inference latency, and model staleness. All four values are exposed as Prometheus Gauges on `/metrics` within 5 minutes of a training cycle completing.

**Independent Test**: After completing a training run (Phase 6), call `GET /admin/ml/metrics` and verify all four top-level sections (`reranker`, `anomaly_detector`, `inference`, `staleness`) contain non-null values. Wait one Prometheus scrape interval and verify all four Gauge metric names appear in `GET /metrics`.

### Tests for User Story 5 (write first — confirm they FAIL)

- [X] T045 [P] [US5] Write failing unit tests for ML metrics in `tests/unit/ml/test_metrics.py`: staleness gauge updates after training completes; p99 latency window returns correct quantile from sliding-window samples; no-model-trained state returns null fields (not 500)
- [X] T046 [P] [US5] Write failing contract tests for `GET /admin/ml/metrics` in `tests/contract/ml/test_admin_api_contracts.py`: 200 schema matches spec (all 4 sections); null fields when no model trained; 401 without API key

### Implementation for User Story 5

- [X] T047 [P] [US5] Register Prometheus Gauges in `src/observability/metrics.py`: `ml_reranker_ndcg_at_10`, `ml_anomaly_detector_f1_score`, `ml_inference_p99_latency_ms`, `ml_model_staleness_seconds` — make T045 pass
- [X] T048 [US5] Implement p99 inference latency sliding-window tracker in `src/ml/reranker.py` and `src/ml/anomaly_detector.py`: record duration after each inference call, update `ml_inference_p99_latency_ms` gauge from a 300-second rolling deque (depends on T047, T017, T022)
- [X] T049 [US5] Update Prometheus staleness gauge and NDCG@10/F1 gauges in `src/ml/training/pipeline.py` on successful training completion (depends on T047, T041)
- [X] T050 [US5] Implement ML metrics API router in `src/api/routers/ml_metrics.py`: `GET /admin/ml/metrics` reading from `ModelRegistry` and in-process gauge values, returns null fields (not 500) when no model exists — make T046 pass (depends on T047, T048, T049)
- [X] T051 [US5] Register ML metrics router in `src/api/main.py` (depends on T050)

**Checkpoint**: All four monitoring metrics visible on dashboard within one scrape interval of training completion. The endpoint returns valid data (with nulls) even before first training run.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Background embedding refresh, telemetry→US3 connector, observability hardening, and quickstart validation.

- [X] T052 Implement background `UserEmbedding` refresh coroutine in `src/ml/feature_store.py`: periodic task (every `embedding_ttl_seconds / 2`) that re-computes embeddings for all active devices using `FeatureEngineer` output and writes to Redis (depends on T016, T037)
- [X] T053 Trigger `Distributor.build_package()` from `TrainingPipeline` after successful model activation in `src/ml/training/pipeline.py`: connects US4 training outcome → US3 distribution artifact (depends on T028, T041)
- [X] T054 [P] Add OpenTelemetry spans to re-ranking and anomaly-detection paths in `src/ml/reranker.py` and `src/ml/anomaly_detector.py` (depends on T017, T022)
- [X] T055 [P] Add structured JSON log entries with correlation IDs to all ML inference paths in `src/ml/reranker.py` and `src/ml/anomaly_detector.py`
- [X] T056 [P] Update `src/db/models/__init__.py` to export all four new ML ORM models so Alembic autogenerate detects them
- [X] T057 [P] Validate quickstart.md: run `make dev` + `make seed` + `POST /admin/ml/retrain` + poll until succeeded + verify `GET /admin/ml/metrics` shows all non-null values — document any discrepancies as issues

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2–US5
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 (but integrates with aggregator, coordinate merge)
- **US3 (Phase 5)**: Depends on Phase 2 — no dependency on US1/US2 for the distributor itself; packaging step in Phase 8 depends on US4
- **US4 (Phase 6)**: Depends on Phase 2 — no dependency on US1/US2/US3 for the pipeline itself; gauges updated in Phase 7 depend on US4 completion
- **US5 (Phase 7)**: Depends on Phase 2 — US5 Prometheus updates depend on US4 (T041) and inference tracking depends on US1 (T017) and US2 (T022)
- **Polish (Phase 8)**: Depends on all user story phases

### User Story Dependencies

| Story | Depends on | Independent of |
|-------|-----------|---------------|
| US1 (P1) | Phase 2 complete | US2, US3, US4, US5 |
| US2 (P2) | Phase 2 complete | US1 (share aggregator — coordinate), US3, US4, US5 |
| US3 (P3) | Phase 2 complete | US1, US2; full package chain needs US4 via Phase 8 |
| US4 (P4) | Phase 2 complete | US1, US2, US3 |
| US5 (P5) | Phase 2 complete; T041 (US4 pipeline) for gauge updates | US1, US2, US3 (metrics endpoint itself) |

### Within Each User Story

1. Write test tasks — confirm they FAIL (constitution Principle II)
2. Implement models/entities
3. Implement services/components
4. Implement API endpoints
5. Confirm tests PASS

---

## Parallel Execution Examples

### Phase 2: Foundational (run T007–T010 in parallel)

```
Parallel batch:
  Task T007: Create TrainingJob ORM model in src/db/models/ml_training_job.py
  Task T008: Create TrainedModel ORM model in src/db/models/ml_trained_model.py
  Task T009: Create AnomalyReading ORM model in src/db/models/ml_anomaly_reading.py
  Task T010: Create OnDeviceModelPackage ORM model in src/db/models/ml_on_device_package.py

Then sequentially:
  Task T011: Write migration 005_ml_tables.py (requires T007–T010)
```

### Phase 3: US1 (write tests in parallel, then implement)

```
Parallel batch (tests — must FAIL first):
  Task T013: unit tests for FeatureStore
  Task T014: unit tests for Reranker
  Task T015: integration test for personalised recommendations

Then:
  Task T016: implement RedisFeatureStore (makes T013 pass)
  Task T017: implement TFLiteReranker (makes T014 pass)
  Task T018: wire into aggregator (makes T015 pass)
```

### Phase 6: US4 (training pipeline has the most parallelism)

```
Parallel batch (tests — must FAIL first):
  Task T031: unit tests for DataExtractor
  Task T032: unit tests for FeatureEngineer
  Task T033: unit tests for Evaluator
  Task T034: contract tests for admin training API

Parallel batch (implementations):
  Task T036: implement DataExtractor (makes T031 pass)
  Task T037: implement FeatureEngineer (makes T032 pass)
  Task T038: implement Evaluator (makes T033 pass)

Then sequentially:
  Task T039: implement ModelTrainer (depends on T037)
  Task T040: implement ModelRegistry (depends on T008 ORM)
  Task T041: implement TrainingPipeline (depends on T036–T040)
  Task T043: implement admin training API (depends on T041)
```

---

## Implementation Strategy

### MVP: User Story 1 Only

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks everything)
3. Complete Phase 3: User Story 1 (re-ranking + cold-start)
4. **STOP and VALIDATE**: Warm device gets re-ranked recommendations; cold-start device gets valid fallback
5. Demo-able: personalised recommendations with relevance scores visible in API response

### Incremental Delivery

1. Setup + Foundational → framework ready
2. + US1 (re-ranking) → personalised recommendations live
3. + US2 (anomaly detection) → safety layer live
4. + US4 (training pipeline) → admin can retrain on demand
5. + US3 (model distribution) → on-device inference enabled
6. + US5 (monitoring dashboard) → production observability complete
7. Polish → embedding refresh, cross-cutting observability

### Parallel Team Strategy (5 engineers)

After Phase 2 completes:
- Engineer A: US1 (re-ranker + feature store)
- Engineer B: US2 (anomaly detector)
- Engineer C: US3 (distributor + distribution API)
- Engineer D: US4 (training pipeline — largest phase, may need 2 engineers)
- Engineer E: US5 (metrics + dashboard) + Phase 8 Polish

---

## Task Summary

| Phase | Tasks | Parallel Opportunities |
|-------|-------|----------------------|
| Phase 1: Setup | T001–T005 | T003, T004, T005 |
| Phase 2: Foundational | T006–T012 | T007–T010 (ORM models) |
| Phase 3: US1 | T013–T019 | T013–T016 (tests + FeatureStore) |
| Phase 4: US2 | T020–T025 | T020–T022 (tests + AnomalyDetector) |
| Phase 5: US3 | T026–T030 | T026, T027, T028 (tests + Distributor) |
| Phase 6: US4 | T031–T044 | T031–T038 (tests + 3 pipeline components) |
| Phase 7: US5 | T045–T051 | T045–T047 (tests + Gauges) |
| Phase 8: Polish | T052–T057 | T054–T057 |
| **Total** | **57 tasks** | **~24 parallelisable** |

---

## Notes

- `[P]` tasks operate on different files with no shared in-progress dependencies — safe to run in parallel
- TDD is mandatory (constitution Principle II): write each test task, confirm red, then implement
- Each user story checkpoint is a valid demo or partial deployment point
- `src/recommendation/aggregator.py` is modified by both US1 (T018) and US2 (T024) — coordinate these on the same branch or merge sequentially
- Alembic migration T011 must run before any integration tests that touch the ML tables
- `model_artifact_dir` and `on_device_package_dir` must exist on disk before training (T005 / `make dev`)
