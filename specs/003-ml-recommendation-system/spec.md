# Feature Specification: ML Recommendation System

**Feature Branch**: `003-ml-recommendation-system`
**Created**: 2026-05-05
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Personalized Recommendation Delivery (Priority: P1)

A device user opens the health dashboard and instead of receiving the same generic recommendations produced by external providers, receives a list re-ordered to reflect their own recent behavioral patterns — with items aligned to their history at the top and irrelevant ones moved down or suppressed.

**Why this priority**: This is the core value proposition of the ML layer. Without personalised re-ranking the system adds no value over raw provider output, making all other stories meaningless.

**Independent Test**: Submit a recommendation request for a user with 7+ days of telemetry history. Verify the returned list contains the same items as the raw provider output but in a different order, with a personal relevance score attached to each item.

**Acceptance Scenarios**:

1. **Given** a user has at least 7 days of recorded telemetry, **When** the recommendation aggregator produces a merged list from all active providers, **Then** the ML layer returns the same items re-ordered by personal relevance score, with each item carrying that score.
2. **Given** a user has fewer than 7 days of telemetry (cold start), **When** recommendations are requested, **Then** the system returns the raw provider ordering without error and without a personal relevance score.
3. **Given** the ML re-ranking service is temporarily unavailable, **When** recommendations are requested, **Then** the system transparently falls back to raw provider ordering and the user receives a valid response within normal response time.

---

### User Story 2 - Anomaly-Aware Recommendation Adjustment (Priority: P2)

A device user is experiencing telemetry readings that deviate significantly from their personal norm — for example, an unusually elevated heart rate. The system detects this condition automatically and adjusts the recommendation set, suppressing advice to intensify physical activity and preserving or promoting recovery-oriented suggestions.

**Why this priority**: Delivering exercise-intensification advice during an anomalous health reading is the primary safety risk of any personalised health recommendation system. Anomaly-aware adjustment must be in place before the personalisation layer is relied upon by users.

**Independent Test**: Submit a telemetry payload containing a heart-rate value well above the user's established personal baseline. Verify that activity-intensification recommendations are absent or scored at zero in the response.

**Acceptance Scenarios**:

1. **Given** a user's telemetry reading is within their personal baseline, **When** the anomaly detector evaluates it, **Then** the anomaly score is below the suppression threshold and no recommendations are modified.
2. **Given** a user's telemetry reading significantly deviates from their personal baseline, **When** the anomaly detector evaluates it, **Then** an anomaly flag is raised and activity-intensification recommendations are suppressed from the final list.
3. **Given** a new user with no established personal baseline, **When** the anomaly detector evaluates their reading, **Then** no anomaly flags are raised (insufficient data) and recommendations are returned unmodified.
4. **Given** the anomaly detector suppresses all recommendations, **When** the final list is assembled, **Then** the system returns at least one recommendation (the lowest-risk available item) rather than an empty list.

---

### User Story 3 - Offline On-Device Recommendations (Priority: P3)

A device user has no internet connection. Using a locally cached behavioural model and recent telemetry stored on the device, the device re-ranks a cached recommendation list and returns a personalised result within one second.

**Why this priority**: The offline requirement is a hard latency and availability constraint. It depends on the cloud model being trained and distributed first, making it lower priority than cloud-side personalisation, but it is a distinct user-facing capability.

**Independent Test**: Disable network access on the device. Request recommendations. Verify the device returns a ranked list within one second using only locally stored data.

**Acceptance Scenarios**:

1. **Given** the device has a previously distributed model and a local telemetry buffer, **When** there is no internet connection, **Then** the device returns a ranked recommendation list within one second.
2. **Given** the device has never received a distributed model, **When** there is no internet connection, **Then** the device displays the raw unranked recommendation list as a fallback without error.
3. **Given** the device has a model but no recent telemetry in its local buffer, **When** offline inference is requested, **Then** the device uses the last known user profile state and returns a ranked list.
4. **Given** the on-device model format is incompatible with the device's runtime, **When** the device attempts to load it, **Then** the device falls back to the previously compatible model version and the platform logs the compatibility failure.

---

### User Story 4 - Admin-Triggered Model Retraining (Priority: P4)

An admin navigates to the Admin Config section of the platform dashboard, clicks the "Retrain Models" button, and initiates the full training pipeline. The pipeline reads fresh telemetry and provider response data, trains and evaluates both models, and deploys the updated versions. The admin receives a progress indicator and a completion notification with the resulting quality metrics.

**Why this priority**: Retraining on fresh data is the mechanism that keeps personalisation accurate over time. The admin trigger enables on-demand updates and is the operational entry point for this capability.

**Independent Test**: Click "Retrain Models" from the admin UI. Verify that a training job is initiated, completes without error, the deployed model version number increments, and the staleness counter resets.

**Acceptance Scenarios**:

1. **Given** sufficient training data exists, **When** the admin clicks "Retrain Models," **Then** a training job starts, the admin sees a progress indicator, and receives a completion notification with quality metrics (NDCG@10 and F1 score).
2. **Given** a training job is already running, **When** the admin clicks "Retrain Models" again, **Then** the request is rejected with a clear message ("Training already in progress") and no duplicate job is started.
3. **Given** the training pipeline fails mid-run, **When** the failure occurs, **Then** the previously deployed model remains active, the admin receives a failure notification with the error reason, and the training job is marked failed.
4. **Given** a training job completes successfully, **When** the admin views the ML metrics dashboard, **Then** the model version increments, the staleness counter resets, and updated NDCG@10 and F1 values are displayed.

---

### User Story 5 - ML Quality Monitoring Dashboard (Priority: P5)

A platform operator opens the ML monitoring section of the observability dashboard and sees four live panels: re-ranker ranking quality (NDCG@10), anomaly detector accuracy (F1 score), inference latency at the 99th percentile, and model staleness (time elapsed since last successful training). The operator uses this view to detect model degradation or data drift before it affects users.

**Why this priority**: Observability is a supporting capability that enables operators to maintain confidence in the models over time. It does not block any user-facing functionality but is necessary for production operation.

**Independent Test**: After a completed training cycle, open the ML dashboard and verify all four panels show current, non-zero values. Verify the staleness panel increments over time and resets after a subsequent retraining.

**Acceptance Scenarios**:

1. **Given** models have been trained and deployed, **When** the ML dashboard is viewed, **Then** all four panels (NDCG@10, F1, p99 latency, staleness) display current values without error.
2. **Given** a model has just been retrained, **When** the dashboard refreshes, **Then** the staleness panel resets to zero and the NDCG@10 and F1 panels show the latest training evaluation values.
3. **Given** inference latency increases beyond acceptable levels, **When** the p99 latency panel updates, **Then** the operator can observe the current value and take action before user experience is impacted.

---

### Edge Cases

- What happens when a user has fewer than 7 days of telemetry (cold start)? → Raw provider ordering is used; no personal relevance scores are attached; the user receives a valid response.
- What happens when the anomaly detector suppresses every recommendation? → A minimum of one recommendation (the lowest-risk item) is always returned.
- What happens when the user embedding cannot be retrieved in time for an inference request? → The system falls back to raw ordering for that request, logs the cache miss, and recomputes the embedding asynchronously.
- What happens when both external providers return empty lists? → The ML layer has no items to rank and returns an empty list gracefully, without error.
- What happens when the training pipeline is triggered while one is already running? → The new request is rejected with a clear status message; no duplicate job is created.
- What happens when the on-device model is incompatible with a device runtime version? → The device falls back to the most recent compatible model version; the incompatibility is logged on the platform.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST re-rank the merged recommendation list produced by external providers for each user, using that user's behavioural history from the preceding 7 to 30 days.
- **FR-002**: The system MUST attach a personal relevance score to each recommendation in the re-ranked output.
- **FR-003**: The system MUST fall back to raw provider ordering — without error — when a user has fewer than 7 days of recorded telemetry history.
- **FR-004**: The system MUST fall back to raw provider ordering — without error — when the ML re-ranking service is unavailable.
- **FR-005**: The system MUST evaluate each incoming telemetry reading against that user's personal behavioural baseline and produce an anomaly score between 0 and 1 for that reading.
- **FR-006**: The system MUST suppress activity-intensification recommendations when the anomaly score for the current reading exceeds the configured suppression threshold.
- **FR-007**: The system MUST always return at least one recommendation; it MUST NOT return an empty list solely due to anomaly suppression.
- **FR-008**: The system MUST apply no anomaly flags for users with fewer than 7 days of personal baseline data (insufficient data default: no flags raised).
- **FR-009**: The system MUST support on-device inference without requiring an active internet connection, using a locally stored model and telemetry buffer.
- **FR-010**: On-device inference MUST complete and return a ranked recommendation list within 1 second for 99% of requests on target device hardware.
- **FR-011**: Updated on-device models MUST be distributed to devices during scheduled device sync events, up to 10 times per day.
- **FR-012**: If no on-device model has ever been received, the device MUST fall back to displaying the raw unranked recommendation list.
- **FR-013**: The training pipeline MUST execute the following ordered steps: data extraction from telemetry and provider response archives, feature engineering, model training, evaluation against a holdout set, and model registration.
- **FR-014**: The training pipeline MUST train and evaluate both the re-ranker and the anomaly detector within a single pipeline run.
- **FR-015**: The admin dashboard MUST provide a clearly labelled "Retrain Models" control that, when activated, initiates the full training pipeline.
- **FR-016**: The system MUST prevent concurrent training runs; activating retraining while a job is in progress MUST be rejected with a clear status message.
- **FR-017**: The system MUST pre-compute and cache per-user behavioural feature vectors so that their retrieval does not become the dominant contributor to inference latency.
- **FR-018**: The system MUST expose the following metrics for operational monitoring: re-ranker NDCG@10, anomaly detector F1 score, p99 inference latency, and model staleness (elapsed time since last successful training).
- **FR-019**: The system MUST log every training job with its outcome (succeeded/failed), duration, triggering actor, and resulting quality metrics.
- **FR-020**: The system MUST retain the previously active model version so that a rollback to that version can be performed without re-training in the event of post-deployment degradation.

### Key Entities

- **UserEmbedding**: A numerical vector summarising a user's behavioural profile, derived from 7–30 days of telemetry history. Subject to time-based expiry; refreshed by the feature computation pipeline. Associated with a single device/user.
- **RecommendationItem**: A single recommendation with its source provider, original provider score, personal relevance score assigned by the re-ranker, and an anomaly suppression flag.
- **AnomalyReading**: A per-device, per-reading record containing the anomaly score, whether the suppression threshold was exceeded, the evaluated telemetry fields, and the timestamp.
- **TrainedModel**: A versioned model artifact with training timestamp, evaluation metrics (NDCG@10 or F1 as applicable), deployment status (active / archived / failed), and a reference to its predecessor version for rollback.
- **OnDeviceModelPackage**: A compressed, distribution-ready model artifact intended for deployment to devices. Contains a version identifier, creation timestamp, and compatibility metadata.
- **TrainingJob**: A record of a single training pipeline execution with status (running / succeeded / failed), start and end times, the actor that triggered it, and a reference to the resulting TrainedModel if successful.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users with at least 7 days of behavioural history receive recommendation lists where the top-ranked item is measurably more relevant than the top item from raw provider ordering, as evidenced by a positive NDCG@10 improvement over the raw-ordering baseline after 30 days of accumulated history.
- **SC-002**: On-device inference produces a ranked recommendation list within 1 second for 99 out of every 100 requests, regardless of internet connectivity.
- **SC-003**: The anomaly detector achieves an F1 score of 0.80 or above when evaluated against a labelled holdout set of anomalous telemetry readings.
- **SC-004**: The full training pipeline — from trigger to deployed model — completes within 60 minutes, enabling multiple retraining cycles per day.
- **SC-005**: Model staleness does not exceed 24 hours under normal operating conditions (assuming at least one admin-triggered retraining cycle per day).
- **SC-006**: An admin can initiate a retraining cycle and view the resulting quality metrics in under 5 minutes of active interaction, without technical assistance.
- **SC-007**: Cold-start users (fewer than 7 days of history) receive recommendations without errors, without degraded response times, and without any visible indication of fallback behaviour.
- **SC-008**: All four operational monitoring metrics (NDCG@10, F1, p99 latency, staleness) are visible on the platform dashboard within 5 minutes of a completed training cycle.

## Assumptions

- **A-001**: The ingestion pipeline already captures and stores telemetry fields (heart rate, steps, sleep duration, activity level) in the event archive; no new data capture work is required for this feature.
- **A-002**: Provider response logs (service1 and service2 outputs, including recommendation text, confidence, title, details, and priority) are written to a dedicated archive as part of the existing aggregation flow; this archive is available as a data source for training.
- **A-003**: Per-user feature vectors are cached in the existing in-memory cache infrastructure with a TTL of approximately 5 minutes; this infrastructure is shared and already deployed.
- **A-004**: On-device model distribution uses the existing device sync protocol; this feature defines what is pushed (the model artefact and version metadata), not the transport mechanism.
- **A-005**: The anomaly suppression threshold defaults to 0.5 on a 0–1 scale and is configurable per deployment without a code change.
- **A-006**: Training labels for the re-ranker are derived from provider output consistency and session-level engagement signals (not explicit user ratings, which are unavailable); label quality is therefore approximate.
- **A-007**: "Retrain Models" triggers a single pipeline run that trains both the re-ranker and the anomaly detector; there is no separate per-model trigger in the initial release.
- **A-008**: Model versions are assigned sequential integers; rolling back means re-activating the most recent archived version, not re-running training.
- **A-009**: The ML monitoring dashboard is built as an extension of the existing platform observability dashboard; no separate monitoring infrastructure is required.
- **A-010**: The minimum data requirement for establishing a personal anomaly baseline is 7 days; users below this threshold receive no anomaly detection (safe default: no flags raised, no suppression applied).
