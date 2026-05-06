# Feature Specification: Health Intelligence Platform PoC

**Feature Branch**: `001-health-intelligence-poc`
**Created**: 2026-05-04
**Status**: Draft
**Input**: User description: "Build an application that will support health intelligence platform.
Requirements are given. I need a small PoC, assuming most of things and trying to stick to AWS
services but it is allowed to use any kind of open-source tools. We need to clarify all services
in PoC before planning and implementing. Major parts - backend is Python-oriented."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest Telemetry & Receive Recommendations (Priority: P1)

A user with a registered fitness device sends health measurements (height, weight, activity data)
to the platform and instantly receives personalised health recommendations aggregated from multiple
external intelligence providers. The recommendations are normalised, filtered by confidence,
grouped by type, and sorted by priority before being returned.

**Why this priority**: This is the core value proposition of the platform. Every other story builds
on top of this ingest-and-recommend loop. Without it the PoC cannot be demonstrated.

**Independent Test**: Invoke the recommendation API with sample device measurements.
Verify that at minimum two provider responses are merged, normalised, and returned as a ranked
list within 1 second, without requiring any other story to be complete.

**Acceptance Scenarios**:

1. **Given** a registered device with valid measurements (height, weight),
   **When** the device calls the recommendation API,
   **Then** the system returns a merged, sorted list of health recommendations in under 1 second.

2. **Given** two providers with overlapping recommendation text,
   **When** their responses are aggregated,
   **Then** recommendations with the same short text are grouped and the highest priority/confidence
   value is surfaced.

3. **Given** one provider returns an error,
   **When** the recommendation API is called,
   **Then** results from the healthy provider are still returned and the error is logged with a
   trace ID.

4. **Given** a third provider endpoint with a different API token is configured,
   **When** the recommendation API is called,
   **Then** results from all three providers are merged into the unified response.

---

### User Story 2 - Device Registration & Digital Twin Management (Priority: P2)

An operator or device SDK registers a new fitness device with the platform, assigning it a unique
identity, recording its hardware metadata, and creating a corresponding digital-twin entry in the
cloud registry so the device state can be tracked and synced.

**Why this priority**: Device registration is a prerequisite for credit tracking and personalised
recommendations tied to device identity, but the recommendation flow (US1) can be demonstrated
with a pre-seeded device, so this story is P2.

**Independent Test**: Register a new device via the API, then fetch its twin state.
Verify the twin is created with correct metadata and an initial credit balance without needing
US3 or US4 to be complete.

**Acceptance Scenarios**:

1. **Given** a new device with model, firmware version, and OS metadata,
   **When** the device calls the registration endpoint,
   **Then** a unique device ID and twin record are created and the initial credit balance is set.

2. **Given** an already-registered device,
   **When** the registration endpoint is called again with the same device fingerprint,
   **Then** the existing twin is returned (idempotent) and no duplicate is created.

3. **Given** a registered device,
   **When** the operator requests the twin state,
   **Then** the current metadata and credit balance are returned accurately.

---

### User Story 3 - Credits Tracking & Reward Tier Assignment (Priority: P3)

Each recommendation request consumes credits from the requesting device's balance. As a device
accumulates usage, its reward tier (Bronze → Silver → Gold → Platinum) is recalculated
automatically, unlocking higher-priority recommendation features.

**Why this priority**: Credits and tiers add business logic on top of US1 and US2. The core
recommendation loop works without them; they enrich the experience.

**Independent Test**: Seed a device with a credit balance, trigger recommendation requests,
and verify the balance decrements and the tier updates at the correct thresholds without
needing US4.

**Acceptance Scenarios**:

1. **Given** a device with 100 credits,
   **When** a recommendation request consuming 10 credits is made,
   **Then** the credit balance is decremented to 90 and the tier is recalculated.

2. **Given** a device whose cumulative usage crosses the Silver threshold,
   **When** the next recommendation request is processed,
   **Then** the device's reward tier is updated to Silver in the twin record.

3. **Given** a device with zero credits,
   **When** a recommendation request is attempted,
   **Then** the request is rejected with a clear insufficient-credits error and no recommendation
   is returned.

---

### User Story 4 - Real-Time Observability Dashboard (Priority: P4)

Platform operators can view a live dashboard showing key health metrics: ingestion throughput,
recommendation latency, active device count, credit consumption rate, and any anomalous
telemetry events. The dashboard reflects data within seconds of events occurring.

**Why this priority**: Observability is a non-functional requirement and a PoC demonstration
asset. The platform functions without it; it is the last piece to add.

**Independent Test**: Trigger several ingestion and recommendation events, then open the
metrics endpoint / dashboard. Verify at least three distinct metrics are visible and update
in near-real time.

**Acceptance Scenarios**:

1. **Given** active telemetry ingestion,
   **When** the operator opens the metrics endpoint,
   **Then** current request counts, error rates, and p95 latency are visible.

2. **Given** an anomalous telemetry record is quarantined,
   **When** the dashboard is viewed,
   **Then** the anomaly count metric increments and a log entry with trace ID is accessible.

---

### Edge Cases

- What happens when all configured recommendation providers are unavailable simultaneously?
- How does the system handle a telemetry payload with missing mandatory fields?
- What if a device sends a batch sync with events timestamped more than 24 hours in the past?
- How does the system behave when two providers return conflicting recommendations with equal
  priority and confidence?
- What happens when the credit balance goes negative due to a concurrent deduction race condition?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept health telemetry from simulated devices via an HTTP/REST
  `/ingest` endpoint on port 9000, using the simulator's JSON payload schema (heart rate,
  SpO₂, steps, GPS, temperature, blood pressure, stress, hydration, battery percentage,
  device type, user ID, scenario, firmware version, and anomaly flag).
- **FR-002**: System MUST accept health telemetry published by the Device Simulator via MQTT
  to the `health/telemetry/{device_id}` topic on AWS IoT Core, using X.509 mTLS
  authentication (JITR flow).
- **FR-003**: System MUST query at least two external recommendation providers concurrently and
  aggregate their responses within a single API call.
- **FR-004**: System MUST normalise heterogeneous provider response formats (Service1 confidence
  model, Service2 priority model) into a unified internal recommendation schema.
- **FR-005**: System MUST filter aggregated recommendations by a configurable minimum confidence
  threshold.
- **FR-006**: System MUST group recommendations sharing the same short text and surface the
  highest priority/confidence value for each group.
- **FR-007**: System MUST sort the final recommendation list by priority (descending).
- **FR-008**: System MUST support a third recommendation provider endpoint with a distinct API
  token, following the same adapter pattern as the first two.
- **FR-009**: System MUST register devices with metadata (model, firmware, OS, capabilities)
  and a biometric profile (height in cm, weight in kg), and create a corresponding
  digital-twin record. The ingestion pipeline MUST use the stored biometric profile to
  enrich recommendation provider calls when processing telemetry for that device.
- **FR-010**: System MUST track a credit balance per device, decrement it on each chargeable
  action, and reject actions when the balance is zero.
- **FR-011**: System MUST dynamically compute and persist a reward tier (Bronze / Silver / Gold /
  Platinum) for each device based on cumulative credit consumption thresholds.
- **FR-012**: System MUST validate incoming telemetry records and quarantine those failing
  validation with a structured error record and trace ID.
- **FR-013**: System MUST expose a metrics endpoint returning current ingestion throughput,
  recommendation latency (p50/p95), error rate, and active device count.
- **FR-014**: System MUST support a simulated batch-sync mode where a device submits multiple
  telemetry events in a single request (representing offline accumulation).
- **FR-015**: System MUST emit structured, correlation-ID-tagged logs for every ingestion and
  recommendation request.
- **FR-016**: The repository MUST include AWS CloudFormation templates that provision all
  required AWS infrastructure (Kinesis stream, IoT Core resources, IAM roles/policies,
  compute, and supporting services) in a target AWS account.
- **FR-017**: The repository MUST include a shell bootstrap script that orchestrates
  CloudFormation stack deployment in the correct order and performs any post-deployment
  initialisation steps (e.g., IoT certificate provisioning, test device seeding).

### Key Entities

- **Device**: Unique identity, hardware metadata (model, firmware, OS), credit balance,
  reward tier, registration timestamp, twin state, user biometric profile (height in cm,
  weight in kg) stored at registration and used to enrich outgoing recommendation requests.
- **TelemetryEvent**: Device ID, ingestion timestamp, measurement payload, source protocol,
  validation status, trace ID.
- **RecommendationRequest**: Device ID, input measurements, requested providers, trace ID,
  timestamp.
- **Recommendation**: Provider ID, raw confidence (0–1), raw priority (1–1000), normalised
  score, short text, detail text.
- **AggregatedRecommendation**: Short text (group key), maximum normalised score, contributing
  source list.
- **CreditTransaction**: Device ID, amount (positive = top-up, negative = spend), action type,
  resulting balance, timestamp.
- **RewardTier**: Bronze (0–999 pts) / Silver (1,000–4,999 pts) / Gold (5,000–19,999 pts) /
  Platinum (20,000+ pts) mapped to cumulative credit spend.
- **IngestionBatch**: Batch ID, device ID, event list, submission timestamp, processing status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A registered device can obtain aggregated health recommendations within 1 second
  of submitting measurements (end-to-end, measured at the API boundary).
- **SC-002**: Recommendations from at least two providers are always merged in a single
  response; the third provider integrates without changes to the core aggregation logic.
- **SC-003**: Credit balance for a device correctly reflects all deductions after 100
  consecutive recommendation requests with no race-condition discrepancies.
- **SC-004**: Reward tier transitions (Bronze → Silver → Gold → Platinum) occur automatically
  and are observable in the twin record within the same request that crosses the threshold.
- **SC-005**: At least 95% of invalid telemetry records are quarantined with a structured
  error and do not affect processing of valid records in the same batch.
- **SC-006**: The full PoC environment starts from a single command; a built-in data generator
  produces at least 10 devices with realistic telemetry within 2 minutes of startup.
- **SC-007**: At least four distinct platform metrics (throughput, latency, error rate, active
  devices) are visible and update within 5 seconds of new activity.

## Clarifications

### Session 2026-05-04

- Q: What infrastructure-as-code and provisioning mechanism is required? → A: AWS CloudFormation
  templates for all AWS resources plus a shell bootstrap script that deploys stacks in order and
  handles post-deployment steps (certificate provisioning, test device seeding).
- Q: What compute target should host the Python backend? → A: ECS Fargate + Application Load
  Balancer; containerised FastAPI service, no cold starts, ALB as the ingress point.
- Q: How should the Kinesis stream topology be structured? → A: Single stream with event type
  (telemetry / recommendation / credits) used as the partition key; one CloudFormation resource,
  one IAM policy, fan-out handled in application logic.
- Q: How should CloudFormation templates be structured? → A: Nested stacks per domain —
  separate templates for networking (VPC, subnets, security groups), IAM (roles, policies),
  IoT (IoT Core resources, JITR Lambda), streaming (Kinesis), compute (ECS cluster, task
  definitions, ALB, ECR), and observability (Prometheus, Grafana); a root stack links them.
  The bootstrap script deploys stacks in dependency order.
- Q: How should height and weight be supplied to recommendation providers given the simulator
  does not include them in telemetry events? → A: Height and weight are stored in the
  device/user profile at registration time; the ingestion pipeline enriches outgoing provider
  calls by looking up the stored profile, so the simulator never needs to resend biometrics.
- Q: What should the bootstrap script provision in AWS IoT Core? → A: IoT Core infrastructure
  only — register the CA certificate, create IoT policies, and optionally deploy a JITR Lambda.
  The existing Device Simulator manages its own per-device X.509 cert generation and registers
  devices via JITR on first MQTT connect; no pre-provisioned Things are needed.

## Assumptions

- **AWS region**: eu-central-1 is the default deployment target for any AWS-managed services
  used in the PoC.
- **Provider authentication**: Service1 uses a static token `service1-dev`; Service2 requires
  a unique GUID per request; a third provider will use a configurable token supplied via
  environment variable.
- **Unit normalisation**: Service1 confidence (0–1) is mapped to a normalised score of
  `confidence × 1000`; Service2 priority (1–1000) is used directly as the normalised score;
  the higher value wins when grouping.
- **Credit thresholds**: 1 credit per recommendation request; tier thresholds are
  Bronze (0), Silver (1,000), Gold (5,000), Platinum (20,000) cumulative credits spent.
- **Offline sync**: Batch events older than 24 hours are accepted but flagged as stale and
  do not trigger real-time recommendations.
- **MQTT for PoC**: A locally running open-source MQTT broker (Mosquitto or EMQX) is
  sufficient for the PoC; no managed AWS IoT Core MQTT endpoint is required at this stage.
- **Data generator**: The simulated device generator uses pre-defined height/weight profiles
  and does not require real sensor hardware.
- **Security for PoC**: TLS and AES-256 encryption are architecturally designed and
  documented; for local PoC execution, plaintext transport is acceptable with a clear
  upgrade path noted.
- **Compute**: The Python FastAPI backend runs on ECS Fargate with an Application Load Balancer
  as the ingress point. Docker Compose is used for local development; the CloudFormation
  template provisions the ECS cluster, task definition, service, and ALB.
- **Stream processing**: AWS Kinesis Data Streams is the event bus for the PoC. A single stream
  is provisioned; telemetry, recommendation, and credit events are differentiated by partition
  key. The ingestion layer publishes to this stream; downstream consumers (recommendation
  trigger, anomaly detector) read from it and branch on event type.
- **CloudFormation structure**: Nested stacks per domain — networking, IAM, IoT, streaming,
  compute, and observability. A root stack references all nested stacks as resources. The
  shell bootstrap script deploys stacks in dependency order: networking → IAM → IoT/streaming
  (parallel) → compute → observability, then runs post-deployment initialisation.
- **Digital twin registry**: AWS IoT Core is used for device registration, shadow state, and
  metadata management. All device twin operations go through the IoT Core APIs; cloud
  credentials (AWS account) are required to run the PoC end-to-end.
- **Device Simulator**: An existing Device Simulator application is available at
  `../simulator` (relative to the ingestion pipeline root). It sends telemetry via HTTP to
  `http://host.docker.internal:9000/ingest` and via MQTT to the IoT Core endpoint. The
  simulator auto-seeds 1,000 devices, generates per-device X.509 certificates, and supports
  JITR (Just-In-Time Registration) for automatic IoT Core activation on first MQTT connect.
  The ingestion API MUST expose a `/ingest` endpoint on port 9000 compatible with the
  simulator's payload schema (rich health metrics: heart rate, SpO₂, steps, GPS, temperature,
  blood pressure, stress, hydration, battery).
- **IoT bootstrap scope**: The bootstrap script registers the CA with AWS IoT Core and creates
  the required IoT policies. It does NOT pre-provision individual Things — the simulator
  handles device registration autonomously via JITR.
- **Observability dashboard**: Prometheus metrics endpoint + Grafana running in Docker Compose.
  A Grafana instance is included in the PoC demo environment with dashboards for ingestion
  throughput, recommendation latency, error rates, and active device count.
