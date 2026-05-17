# Research: ML Recommendation System

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-05-05

## Decision 1: Server-Side ML Inference Engine

**Decision**: Use `tflite-runtime` (Python package) for server-side inference, with models trained in TensorFlow 2.x and exported to TFLite flatbuffer format.

**Rationale**: Constitution VII mandates TFLite for on-device inference. Using TFLite on both server and device means a single model format covers both targets, eliminating format-conversion risk between training and deployment. TFLite inference on CPU completes in microseconds for models of this scale (<5 MB), keeping end-to-end recommendation latency well within the 1 s p95 SLA (Constitution IV). `tflite-runtime` is available on Linux x86_64 via pip and avoids pulling in the full TensorFlow runtime in the inference service image.

**Alternatives considered**:
- **ONNX Runtime**: Cross-framework, well-supported. Rejected because constitution explicitly mandates TFLite; operating two inference formats increases operator and testing complexity with no PoC benefit.
- **Scikit-learn (LightGBM / XGBoost)**: Excellent tabular re-ranking performance. Rejected because these frameworks do not produce TFLite artifacts compatible with on-device distribution (FR-009, FR-011).
- **Torch Mobile (TorchScript)**: Strong mobile support. Rejected — constitution mandates TFLite, not TorchScript.

---

## Decision 2: Re-Ranker Model Architecture

**Decision**: Two-tower dot-product model (user embedding tower × item embedding tower) trained with a pairwise ranking loss (BPR / LambdaRank). Training labels derived from provider output consistency and session-level engagement signals (per A-006, explicit user ratings are unavailable).

**Rationale**: The two-tower architecture produces a fixed-dimension `UserEmbedding` that can be pre-computed offline and cached in Redis (FR-017, A-003). At inference time, only the item tower scores each candidate — the user vector is a Redis cache lookup costing ~1 ms. This makes inference latency proportional to the recommendation list length (typically 5–20 items), not to the 7–30 day telemetry history, keeping the recommendation path within the 1 s p95 SLA. The architecture is also compatible with TFLite export: the user tower produces a vector; the scoring tower is a dot product plus sigmoid, both TFLite-friendly ops.

**Alternatives considered**:
- **Transformer / attention-based sequential recommender**: Higher quality for long sequences. Rejected for PoC — the NDCG@10 improvement target (SC-001) is achievable with two-tower on 7–30 day windows, and attention inference latency is harder to bound at p99.
- **Matrix factorisation (collaborative filtering)**: Simple and well-understood. Rejected because it produces per-user item scores that cannot easily integrate the anomaly suppression logic or the item-level personal relevance score required by FR-002.
- **BM25 / TF-IDF re-ranking**: Text-similarity approach. Rejected — provider recommendations are structured objects with confidence/priority scores, not free-text queries; semantic similarity is not the primary relevance signal here.

---

## Decision 3: Anomaly Detector Model Architecture

**Decision**: Per-user Z-score baseline for the primary anomaly score. Each user's rolling mean and standard deviation per telemetry feature (heart rate, steps, sleep duration, activity level) are computed over the 7–30 day window. Anomaly score = sigmoid of the maximum normalised deviation across evaluated features. Users with fewer than 7 days of history receive no score (undefined → no flag raised, FR-008, A-010). An LSTM autoencoder is trained as the model artifact to generalise beyond simple Z-score when evaluation shows F1 < 0.80 on the holdout set.

**Rationale**: Z-score is interpretable, computable per-user from summary statistics (mean + std per feature), and aligns naturally with the "personal baseline" concept in FR-005. The LSTM autoencoder provides the F1 ≥ 0.80 insurance for the holdout evaluation (SC-003) in cases where physiological patterns are non-linear. Both approaches export cleanly to TFLite. The sigmoid output maps the raw deviation to the [0, 1] anomaly score required by FR-005.

**Alternatives considered**:
- **Isolation Forest**: Good unsupervised detector. Rejected because it treats all users as samples from one distribution — there is no natural per-user personalised baseline concept.
- **One-class SVM**: Classic approach. Rejected for the same per-user personalisation reason, and because training a separate SVM per user does not scale to 10k+ devices.
- **Static threshold rules** (e.g., heart rate > 180 bpm → anomaly): Fast but brittle. Rejected because FR-005 requires evaluation against the user's *personal* baseline — a trained athlete and a sedentary user have fundamentally different norms.

---

## Decision 4: Training Pipeline Orchestration

**Decision**: A `TrainingPipeline` Python class with injected step objects, executed as an `asyncio` background task in the FastAPI process. Job state persisted in PostgreSQL. No external workflow engine for PoC.

**Rationale**: External orchestrators (Airflow, Prefect, Dagster) are appropriate for production multi-stage pipelines but add a new service and operator complexity unjustified by the PoC scope. The training pipeline is a sequential, single-machine process completing in < 60 minutes (SC-004). Persisting job state in PostgreSQL (already present infrastructure) provides the status tracking needed for FR-015 admin UI feedback without additional dependencies. Concurrent execution prevention (FR-016) is implemented as a partial unique index on `status = 'running'` in the `ml_training_jobs` table.

**Alternatives considered**:
- **Apache Airflow**: Production-grade DAG orchestration. Rejected for PoC — new service, new UI, new operator training required; zero additional PoC value.
- **Celery worker**: Async distributed task queue. Rejected — Redis Streams are already present; adding Celery introduces an additional dependency for what is a single sequential job, not a distributed fan-out.
- **FastAPI `BackgroundTasks`**: Simplest approach. Rejected because `BackgroundTasks` has no persistence or cancellation support. Long-running training jobs need their state tracked across request lifecycles, which `asyncio.create_task` with PostgreSQL state satisfies.

---

## Decision 5: UserEmbedding Cache Strategy

**Decision**: User embedding vectors are pre-computed by a periodic background coroutine (every ~5 minutes), stored in Redis with a TTL of 300 seconds (A-003). On inference cache miss, the system falls back to raw ordering for that request and triggers async embedding recomputation (spec edge case: "user embedding cannot be retrieved in time").

**Rationale**: FR-017 explicitly requires pre-computation and caching of embeddings so their retrieval does not dominate inference latency. Computing an embedding requires reading 7–30 days of telemetry from Delta Lake; doing this inline with an inference request would make latency O(telemetry history) rather than O(1). The 5-minute TTL (A-003) keeps vectors fresh enough for the recommendation loop while staying within Redis memory budget. The cache-miss fallback ensures the system always returns a response (FR-003 cold-start guarantee pattern).

**Alternatives considered**:
- **Compute embedding on every inference request**: Simplest, always fresh. Rejected — embedding computation reads gigabytes of Delta Lake data; this would violate the 1 s p95 SLA for users with long histories.
- **Persistent vector store (Pinecone, Weaviate)**: Production-grade semantic search. Rejected for PoC (proprietary SaaS prohibited by Constitution VII; Redis is already available per A-003).
- **Compute embeddings on telemetry ingest**: Event-driven, always fresh. Rejected — ingest events arrive at high frequency; triggering an embedding recompute on every event creates unbounded load on the feature computation pipeline.

---

## Decision 6: On-Device Model Distribution Format

**Decision**: A ZIP archive containing two TFLite flatbuffer files (re-ranker and anomaly detector) plus a `manifest.json` with version IDs, creation timestamp, minimum TFLite runtime version, and input dimension metadata. Distributed via the existing device sync protocol (A-004) up to 10 times per day (FR-011).

**Rationale**: TFLite `.tflite` flatbuffer is the native format for TFLite runtime on all supported device platforms. The ZIP envelope allows devices to verify version and compatibility before loading, enabling the graceful fallback to the prior compatible model version (FR-012 scenario 4). Package size is typically < 5 MB for two-tower models at this scale, comfortably within typical device sync payload budgets.

**Alternatives considered**:
- **ONNX format**: Cross-framework, broadly supported. Rejected — device runtime is TFLite (constitution mandate); shipping ONNX would require a different runtime on device.
- **Raw `.tflite` binary with no envelope**: Simpler. Rejected because compatibility metadata (FR-011) is required to handle the incompatible model scenario in FR-012 scenario 4 gracefully, and without an envelope there is no version identifier for rollback tracking.

---

## Decision 7: ML Metrics Exposure

**Decision**: Prometheus `Gauge` metrics for NDCG@10, F1, p99 inference latency, and staleness (seconds since last successful training). Updated after each training cycle (NDCG@10, F1, staleness) and after each inference batch (p99 latency, staleness). Exposed on the existing `/metrics` Prometheus endpoint.

**Rationale**: Prometheus + Grafana is the mandated observability stack (Constitution VI). NDCG@10 and F1 are post-training constants until the next training cycle, making `Gauge` (not `Counter` or `Histogram`) the correct type. The p99 latency Gauge is updated from a sliding window tracked in-process. SC-008 requires all four metrics visible within 5 minutes of a completed training cycle, which the Prometheus scrape interval satisfies.

**Alternatives considered**:
- **Custom REST endpoint for ML metrics**: More flexible, directly queryable. Rejected because it duplicates existing Prometheus infrastructure and breaks dashboard consistency; the frontend ML monitoring panel should read from the same Grafana datasource as all other platform metrics.
- **Prometheus Histogram for latency**: More rigorous (avoids quantile inaccuracy). Acceptable alternative but adds cardinality; a Gauge updated from an in-process sliding-window p99 is sufficient for the PoC monitoring use case and avoids Histogram label explosion.
- **Push Gateway**: Useful for short-lived batch jobs. Rejected because the inference service is a long-running process and can expose metrics directly; Push Gateway adds an unnecessary hop.
