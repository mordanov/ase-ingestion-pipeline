# Implementation Plan: ML Recommendation System

**Branch**: `003-ml-recommendation-system` | **Date**: 2026-05-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-ml-recommendation-system/spec.md`

## Summary

Add a machine-learning layer to the existing recommendation aggregator that re-ranks provider output using per-user behavioural embeddings, detects anomalous telemetry readings to suppress unsafe recommendations, enables on-device TFLite inference for offline personalisation, and provides an admin-driven training pipeline with a monitoring dashboard. The approach uses TensorFlow for cloud training, TFLite for edge inference, Delta Lake archives as training data sources, and Redis for low-latency embedding retrieval.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: TensorFlow 2.x (training), tflite-runtime (server and edge inference), scikit-learn (evaluation utilities: NDCG, F1), FastAPI (existing), Redis (existing), Delta Lake / PyArrow (existing)  
**Storage**: PostgreSQL (TrainingJob, TrainedModel, AnomalyReading, OnDeviceModelPackage records), Redis (UserEmbedding cache, TTL ~5 min per A-003), local volume / S3-compatible object store (TFLite model artifacts)  
**Testing**: pytest, pytest-asyncio, httpx  
**Target Platform**: Linux server (cloud training + REST API inference); device edge runtime handled separately by device SDK team via existing sync protocol (A-004)  
**Project Type**: web-service extension — new `src/ml/` module added to the existing FastAPI monolith  
**Performance Goals**: On-device inference p99 < 1 s (FR-010); server-side re-ranking must not push end-to-end latency above 1 s p95 (Constitution IV); full training pipeline < 60 min (SC-004)  
**Constraints**: Cold-start fallback with zero error (FR-003, FR-004, FR-008, FR-012); at-least-one recommendation guarantee (FR-007); concurrent training prevention (FR-016); model rollback without re-training (FR-020)  
**Scale/Scope**: 10k+ devices; 14.4 TB/day telemetry available in existing Delta Lake archive (A-001, A-002); both models trained in a single pipeline run (FR-014)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture (SOLID-First) | ✅ PASS | `src/ml/` is a new bounded module with its own `interfaces.py`. The recommendation aggregator integrates only through `Reranker` and `AnomalyDetector` abstractions — no import of ML internals. No circular deps introduced. |
| II. Test-First Development (NON-NEGOTIABLE) | ✅ PASS | Red-Green-Refactor for all ML components. Unit tests for feature engineering, model wrappers, registry; integration tests for training pipeline and API; contract tests for admin endpoints. |
| III. Protocol-Agnostic Ingestion | ✅ N/A | ML layer reads from Delta Lake archive — not from ingestion adapters. No protocol coupling. |
| IV. Real-Time Performance | ✅ PASS | Embeddings pre-computed and cached in Redis (FR-017, A-003). Server-side TFLite inference completes in microseconds. On-device < 1 s p99 (FR-010). Fallback paths (cold-start, ML unavailable) return immediately. |
| V. Security & Compliance | ✅ PASS | Model artifacts stored encrypted at rest. No PII embedded in model weights. Training data uses the existing compliant telemetry archive (already AES-256, HIPAA-annotated). |
| VI. Observability & Data Quality | ✅ PASS | FR-018 mandates NDCG@10, F1, p99 latency, staleness as Prometheus Gauges. FR-019 mandates structured training job logs. All four metrics wired to existing Prometheus endpoint. |
| VII. Open-Source & Cloud-Native First | ✅ PASS | TFLite mandated for edge inference (constitution explicit). TensorFlow for cloud training. Delta Lake for data archive. scikit-learn for evaluation. All open-source; no proprietary SaaS. |

*Post-Phase 1 re-check: All gates still PASS. No violations. No Complexity Tracking entries required.*

## Project Structure

### Documentation (this feature)

```text
specs/003-ml-recommendation-system/
├── plan.md                      # This file
├── research.md                  # Phase 0 output
├── data-model.md                # Phase 1 output
├── quickstart.md                # Phase 1 output
├── contracts/
│   ├── admin-training-api.md    # Phase 1 output
│   ├── ml-metrics-api.md        # Phase 1 output
│   └── model-distribution.md   # Phase 1 output
└── tasks.md                     # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/
├── ml/
│   ├── __init__.py
│   ├── interfaces.py              # Abstract: Reranker, AnomalyDetector, FeatureStore, ModelRegistry
│   ├── feature_store.py           # Redis-backed UserEmbedding cache implementation
│   ├── reranker.py                # TFLite server-side re-ranking inference
│   ├── anomaly_detector.py        # TFLite server-side anomaly scoring
│   ├── registry.py                # TrainedModel CRUD + artifact path management
│   ├── distributor.py             # OnDeviceModelPackage builder (ZIP + metadata)
│   └── training/
│       ├── __init__.py
│       ├── pipeline.py            # Orchestrates full training run (FR-013, FR-014)
│       ├── data_extractor.py      # Reads from Delta Lake telemetry + recommendations archives
│       ├── feature_engineer.py    # Telemetry events → per-user feature vectors
│       ├── model_trainer.py       # TF model training for re-ranker and anomaly detector
│       └── evaluator.py           # NDCG@10 (re-ranker) + F1 (anomaly detector)
├── api/routers/
│   ├── ml_training.py             # POST /admin/ml/retrain, GET /admin/ml/training-jobs/{id}
│   └── ml_metrics.py              # GET /admin/ml/metrics
└── db/models/
    ├── ml_training_job.py         # TrainingJob ORM model
    ├── ml_trained_model.py        # TrainedModel ORM model
    ├── ml_anomaly_reading.py      # AnomalyReading ORM model
    └── ml_on_device_package.py    # OnDeviceModelPackage ORM model

tests/
├── unit/
│   └── ml/
│       ├── test_feature_store.py
│       ├── test_reranker.py
│       ├── test_anomaly_detector.py
│       ├── test_registry.py
│       ├── test_distributor.py
│       └── training/
│           ├── test_feature_engineer.py
│           └── test_evaluator.py
├── integration/
│   └── ml/
│       ├── test_training_pipeline.py
│       └── test_ml_api.py
└── contract/
    └── ml/
        └── test_admin_api_contracts.py

src/db/migrations/versions/
└── 005_ml_tables.py               # New migration: ml_training_jobs, ml_trained_models,
                                   #   ml_anomaly_readings, ml_on_device_packages
```

**Structure Decision**: Single-project extension. The `src/ml/` module is self-contained with its own abstract interfaces. The existing `src/recommendation/aggregator.py` integrates with ML via DI, receiving `Reranker` and `AnomalyDetector` through its constructor. No new top-level project is introduced (constitution PoC scope; 3-project maximum not relevant here — this is a single service).

## Complexity Tracking

> No constitution violations. Table omitted per template guidance.
