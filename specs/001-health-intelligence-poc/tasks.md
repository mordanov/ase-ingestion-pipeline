---
description: "Task list for Health Intelligence Platform PoC"
---

# Tasks: Health Intelligence Platform PoC

**Input**: Design documents from `specs/001-health-intelligence-poc/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/ ✅, research.md ✅

**Testing**: TDD is **NON-NEGOTIABLE** per Constitution Principle II. Test tasks appear
**before** their corresponding implementation tasks in every phase. No implementation task
may be started until its test task is committed and confirmed failing (Red).

**Organization**: Phases follow user story priority (P1 → P4). Each story is independently
testable and deployable. Infrastructure phase runs in parallel with story completion.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- File paths are relative to the repository root

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Scaffold project structure so all subsequent tasks have a consistent file tree.

- [X] T001 Create full project directory structure per plan.md (`src/`, `tests/`, `infra/`, subdirs)
- [X] T002 Create `pyproject.toml` with all dependencies (FastAPI, pydantic, SQLAlchemy asyncpg, boto3, httpx, structlog, opentelemetry-sdk, prometheus-client, aiomqtt, alembic, pytest, pytest-asyncio, moto, ruff, mypy)
- [X] T003 [P] Create `Dockerfile` (python:3.11-slim, non-root user, `src/` on PYTHONPATH)
- [X] T004 [P] Create `.env.example` with all required env vars (LOCAL_DEV, DB url, Redis, AWS region, provider tokens, API_KEY, IoT config)

**Checkpoint**: `python -m pip install -e .` succeeds; all source directories exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create `src/config.py` — Pydantic `BaseSettings` with all env-driven config fields (LOCAL_DEV flag, DB_URL, REDIS_URL, AWS_REGION, provider tokens, API_KEY, Kinesis stream name, IoT endpoint)
- [X] T006 [P] Create `src/db/base.py` — SQLAlchemy 2.0 async engine factory, `AsyncSession` factory, declarative `Base`, and `get_db` dependency
- [X] T007 Create `src/db/models/device.py` — `Device` ORM model with all fields from data-model.md (id, device_type, model, firmware_version, os, user_id `[PII]`, height_cm `[PII]`, weight_kg `[PII]`, credit_balance, reward_tier, cumulative_credits_spent, iot_thing_name, registered_at, updated_at)
- [X] T008 [P] Create remaining ORM models: `src/db/models/telemetry.py` (TelemetryEvent + IngestionBatch), `src/db/models/recommendation.py` (RecommendationRequest), `src/db/models/credits.py` (CreditTransaction), `src/db/models/quarantine.py` (QuarantineRecord) — per data-model.md
- [X] T009 Setup Alembic in `src/db/migrations/` and generate initial migration covering all models in FK dependency order (Device → IngestionBatch → TelemetryEvent → RecommendationRequest → CreditTransaction → QuarantineRecord)
- [X] T010 Create `src/api/main.py` — FastAPI app factory (`create_app()`), lifespan context manager (DB pool init + Kinesis consumer start + shutdown), CORS middleware, API key middleware stub
- [X] T011 Create `src/api/dependencies.py` — `get_db` session dependency; empty stubs for adapter injection (filled per story)
- [X] T012 [P] Create `src/observability/logging.py` — structlog JSON renderer, correlation-ID context var, `bind_trace_id()` helper; configure as global logging backend
- [X] T013 Create `docker-compose.yml` — services: `app` (build from Dockerfile, port 8000 + 9000), `postgres` (postgres:15, healthcheck), `redis` (redis:7-alpine), `mosquitto` (eclipse-mosquitto:2, config volume); all connected on `platform-net`
- [X] T014 Create `Makefile` — targets: `dev` (compose up --build -d), `stop`, `test`, `test-unit`, `test-integration`, `test-contract`, `lint` (ruff + mypy), `migrate`, `seed`, `logs`, `gen-ca`

**Checkpoint**: `make dev` starts all four containers healthy; `docker compose ps` shows all green; `curl localhost:8000/` returns 404 (no routes yet).

---

## Phase 3: User Story 1 — Ingest Telemetry & Receive Recommendations (Priority: P1) 🎯 MVP

**Goal**: Device sends health telemetry via HTTP → platform validates, publishes to stream,
enriches with biometric profile, fans out to ≥2 providers concurrently → returns aggregated
ranked recommendations in < 1 second.

**Independent Test**: `POST http://localhost:9000/ingest` with a seeded device payload →
`POST http://localhost:8000/api/v1/devices/{id}/recommendations` → assert aggregated response
with ≥1 grouped recommendation within 1 s. No other user story needed.

### Tests for User Story 1 — write first, confirm failing ⚠️

- [X] T015 [P] [US1] Create `tests/contract/test_service1_contract.py` — live HTTP POST to Service1 endpoint with valid height/weight/token; assert 200, list response, `confidence` in [0,1], `recommendation` non-empty; test error path with invalid token
- [X] T016 [P] [US1] Create `tests/contract/test_service2_contract.py` — live HTTP POST to Service2 endpoint with lbs/feet/birth_date/GUID; assert 200, `recommendations` list, `priority` in [1,1000], `title` non-empty; test error path
- [X] T017 [P] [US1] Create `tests/integration/test_ingest_http.py` — POST `/ingest` single event for seeded device; assert 202, `accepted=1`, `quarantined=0`, event persisted in DB; POST batch of 3 events; POST event with missing `device_id` → assert quarantined
- [X] T018 [P] [US1] Create `tests/integration/test_recommendation_flow.py` — seed device with height/weight; POST `/api/v1/devices/{id}/recommendations`; assert status 200, `recommendations` list sorted by `max_score` desc, `duration_ms` < 1000, `providers_succeeded` non-empty
- [X] T019 [P] [US1] Create `tests/unit/test_validator.py` — unit test `validate_event()`: valid payload passes; missing `device_id` raises `ValidationError`; `is_anomaly=true` accepted with flag; stale timestamp (>24h) sets `is_stale=true`
- [X] T020 [P] [US1] Create `tests/unit/test_normalizer.py` — unit test `normalize_score()`: service1 confidence 0.4 → 400.0; service2 priority 750 → 750.0; unit test `group_and_sort()`: same `short_text` from two providers merged, higher score wins, list sorted desc
- [X] T021 [P] [US1] Create `tests/unit/test_aggregator.py` — unit test `aggregate()`: both providers succeed → merged result; one provider times out (mock) → partial result returned, error logged; all providers fail → 503; assert `asyncio.gather` called concurrently (mock clock)

### Implementation for User Story 1

- [X] T022 [US1] Create `src/ingestion/interfaces.py` — `IngestionAdapter` ABC with `async def parse(request) -> IngestionEvent`; `IngestionEvent` dataclass (device_id, event_id, source_protocol, event_timestamp, payload dict, trace_id, is_batch, batch_id)
- [X] T023 [P] [US1] Create `src/ingestion/adapters/http_adapter.py` — `HttpIngestionAdapter(IngestionAdapter)`; parse simulator single-event and batch JSON payloads into `IngestionEvent`(s); raise `ValidationError` on schema mismatch
- [X] T024 [US1] Create `src/ingestion/validator.py` — `validate_event(event, db_session) -> ValidationResult`; checks: device_id exists in DB (else `UNKNOWN_DEVICE`), event_id uniqueness (idempotency via Redis), timestamp freshness, anomaly flag pass-through; on failure writes `QuarantineRecord`
- [X] T025 [US1] Create `src/ingestion/publisher.py` — `KinesisPublisher` and `LocalRedisStreamsPublisher` both implementing `EventPublisher` ABC; `LocalRedisStreamsPublisher` used when `LOCAL_DEV=true`; `KinesisPublisher` uses `asyncio.to_thread(boto3.put_record, ...)` to avoid blocking
- [X] T026 [P] [US1] Create `src/recommendation/interfaces.py` — `ProviderAdapter` ABC with `async def get_recommendations(height_cm, weight_kg) -> ProviderResult`; `ProviderResult` dataclass (provider_id, recommendations list, error, duration_ms); `RawRecommendation` dataclass (short_text, detail, normalised_score, provider_id)
- [X] T027 [P] [US1] Create `src/recommendation/adapters/service1_adapter.py` — `Service1Adapter(ProviderAdapter)`; POST height(cm)/weight(kg)/token to Service1 endpoint via `httpx.AsyncClient`; map confidence×1000 → normalised_score; handle error response `{errorCode, errorMessage}`
- [X] T028 [P] [US1] Create `src/recommendation/adapters/service2_adapter.py` — `Service2Adapter(ProviderAdapter)`; convert kg→lbs, cm→feet, use GUID session_token per call; POST to Service2; map priority directly as normalised_score; handle error response `{code, error}`
- [X] T029 [US1] Create `src/recommendation/normalizer.py` — `group_and_sort(results: list[RawRecommendation], min_score: float) -> list[AggregatedRecommendation]`; group by `short_text` (case-insensitive, stripped), keep max score, collect provider list, sort by max_score desc, filter below min_score
- [X] T030 [US1] Create `src/recommendation/aggregator.py` — `aggregate(providers, height_cm, weight_kg, timeout=0.8) -> AggregationResult`; `asyncio.gather(*[p.get(h,w) for p in providers], return_exceptions=True)` wrapped in `asyncio.wait_for`; collect partial results on timeout/error; call normalizer
- [X] T031 [US1] Create `src/recommendation/models.py` — `AggregatedRecommendation`, `AggregationResult` (recommendations, providers_called, providers_succeeded, duration_ms) Pydantic models; `ProviderError` model
- [X] T032 [US1] Create `src/api/routers/ingest.py` — `POST /ingest` (port 9000 via separate uvicorn mount or router prefix); bind trace_id; parse via `HttpIngestionAdapter`; validate each event; publish valid events; return 202 with accepted/quarantined counts
- [X] T033 [US1] Create `src/api/routers/recommendations.py` — `POST /api/v1/devices/{device_id}/recommendations`; validate API key; load device profile from DB (height_cm, weight_kg); call `aggregator.aggregate()`; persist `RecommendationRequest`; return `AggregationResult` response
- [X] T034 [US1] Update `src/api/main.py` — mount `ingest_router` (port 9000) and `recommendations_router`; add `httpx.AsyncClient` lifespan; inject async client into provider adapters
- [X] T035 [US1] Update `src/api/dependencies.py` — `get_http_client`, `get_ingestion_adapter`, `get_publisher`, `get_provider_adapters` (returns list of all configured providers), `get_aggregator` DI factories
- [X] T036 [US1] Create `tests/conftest.py` — async pytest fixtures: `async_client` (httpx TestClient for FastAPI app), `db_session` (test DB with rollback), `mock_service1` / `mock_service2` (httpx mock responders), `seeded_device` (pre-inserted Device row with height/weight)

**Checkpoint**: `make test-unit` passes for T019–T021. `make test-integration` passes for T017–T018. `make test-contract` passes for T015–T016. Full US1 independently testable.

---

## Phase 4: User Story 2 — Device Registration & Digital Twin Management (Priority: P2)

**Goal**: Register a device with biometric profile → create IoT Core thing (or local twin) →
return device ID + credit balance + twin state. Idempotent on re-registration.

**Independent Test**: `POST /api/v1/devices` with model/firmware/height/weight → assert 201,
device_id returned, `GET /api/v1/devices/{id}` returns twin state. No US3 or US4 needed.

### Tests for User Story 2 — write first, confirm failing ⚠️

- [X] T037 [P] [US2] Create `tests/integration/test_device_registration.py` — POST `/api/v1/devices` with full payload; assert 201, device_id, credit_balance=100, reward_tier=bronze; POST same device again → assert 200 idempotent, no duplicate; GET `/api/v1/devices/{id}` → assert twin state fields present
- [X] T038 [P] [US2] Create `tests/contract/test_devices_contract.py` — acceptance tests for devices-api.md contract: field presence, PII fields (height_cm, weight_kg) absent from response, 404 for unknown device_id, 422 for missing required fields

### Implementation for User Story 2

- [X] T039 [US2] Create `src/digital_twin/interfaces.py` — `TwinRegistryAdapter` ABC with `async def register(device) -> TwinRecord`, `async def get_state(device_id) -> TwinState`, `async def update_state(device_id, state) -> None`
- [X] T040 [US2] Create `src/digital_twin/local_registry_adapter.py` — `LocalRegistryAdapter(TwinRegistryAdapter)`; uses PostgreSQL `devices` table as twin store; activated when `LOCAL_DEV=true`; `get_state` reads from DB + fabricates `twin_connected=false, twin_last_seen=updated_at`
- [X] T041 [US2] Create `src/digital_twin/iot_core_adapter.py` — `IotCoreAdapter(TwinRegistryAdapter)`; `register`: calls `asyncio.to_thread(boto3_iot.create_thing, ...)` + `attach policy`; `get_state`: calls `get_thing_shadow` and maps to `TwinState`; handles `ResourceAlreadyExistsException` for idempotency
- [X] T042 [US2] Create `src/digital_twin/registry.py` — `DeviceRegistry`; `register_device(payload)`: upsert `Device` row, initialise credit_balance=100, call `TwinRegistryAdapter.register`, return `DeviceResponse` (no PII fields); `get_device_state(device_id)`: merge DB row + twin adapter state
- [X] T043 [US2] Create `src/api/routers/devices.py` — `POST /api/v1/devices` (register + create twin); `GET /api/v1/devices/{device_id}` (twin state); validate API key; delegate to `DeviceRegistry`
- [X] T044 [US2] Update `src/api/main.py` — mount `devices_router`
- [X] T045 [US2] Update `src/api/dependencies.py` — `get_twin_adapter` factory (returns `LocalRegistryAdapter` if `LOCAL_DEV=true`, else `IotCoreAdapter`); `get_device_registry` factory

**Checkpoint**: `make test-integration` passes for T037–T038. US2 independently testable. US1 tests still pass.

---

## Phase 5: User Story 3 — Credits Tracking & Reward Tier Assignment (Priority: P3)

**Goal**: Each recommendation call deducts 1 credit; balance is atomic; tier transitions
Bronze→Silver→Gold→Platinum happen automatically at threshold crossings; zero-balance blocks requests.

**Independent Test**: Seed device with 100 credits → call `/recommendations` 5× → balance=95,
tier=bronze. Manually set cumulative_credits_spent to 999 → call once more → tier=silver.
Attempt with balance=0 → 402 returned.

### Tests for User Story 3 — write first, confirm failing ⚠️

- [X] T046 [P] [US3] Create `tests/unit/test_ledger.py` — unit test `deduct(device_id, amount, db)`: balance decrements correctly; `CHECK >= 0` constraint raises error on overdraft; resulting_balance in transaction matches; concurrent deduction test (two tasks deducting simultaneously → no negative balance)
- [X] T047 [P] [US3] Create `tests/unit/test_tier_engine.py` — unit test `compute_tier(cumulative_spent)`: 0→bronze, 999→bronze, 1000→silver, 4999→silver, 5000→gold, 19999→gold, 20000→platinum; test `apply_tier_if_changed(device, new_tier, db)`: update only on tier change
- [X] T048 [P] [US3] Create `tests/integration/test_credits_tier.py` — seed device with 100 credits; POST `/recommendations` → assert `credits_remaining=99`; repeat to 0 → assert 402; top-up via POST `/api/v1/devices/{id}/credits` → assert new balance; set `cumulative_credits_spent=999` → POST recs → assert tier=silver in response

### Implementation for User Story 3

- [X] T049 [US3] Create `src/credits/models.py` — `RewardTier` enum (bronze/silver/gold/platinum), `TIER_THRESHOLDS` dict, `CreditActionType` enum (recommendation/registration_bonus/top_up)
- [X] T050 [US3] Create `src/credits/ledger.py` — `CreditLedger`; `deduct(device_id, amount, db)`: `SELECT FOR UPDATE` device row, check balance >= amount, decrement balance + increment cumulative_credits_spent, insert `CreditTransaction`, return resulting_balance; `top_up(device_id, amount, db)`: same pattern with positive amount
- [X] T051 [US3] Create `src/credits/tier_engine.py` — `compute_tier(cumulative_spent) -> RewardTier`; `apply_tier_if_changed(device, db) -> bool` (returns True if tier was updated); called after every deduction
- [X] T052 [US3] Update `src/api/routers/recommendations.py` — before calling aggregator: `ledger.deduct(device_id, 1, db)`; catch `InsufficientCreditsError` → 402; after aggregator returns: `tier_engine.apply_tier_if_changed(device, db)`; add `credits_remaining` and `reward_tier` to response
- [X] T053 [US3] Update `src/api/routers/devices.py` — add `POST /api/v1/devices/{device_id}/credits` endpoint; call `ledger.top_up()`; return new balance + tier
- [X] T054 [US3] Update `src/api/dependencies.py` — `get_credit_ledger`, `get_tier_engine` factories

**Checkpoint**: `make test-unit` passes for T046–T047. `make test-integration` passes for T048. US3 independently testable. US1 + US2 tests still pass.

---

## Phase 6: User Story 4 — Real-Time Observability Dashboard (Priority: P4)

**Goal**: Prometheus metrics + Grafana dashboard showing ingestion throughput, recommendation
latency, error rate, active devices — all updating within 5 seconds of new activity.

**Independent Test**: Trigger 5 ingest events + 2 recommendation calls → `GET /metrics` →
assert `ingest_events_total`, `recommendation_duration_seconds`, `recommendation_errors_total`
present and non-zero. Open Grafana at localhost:3000 → dashboard loads with live panels.

### Tests for User Story 4 — write first, confirm failing ⚠️

- [X] T055 [P] [US4] Create `tests/integration/test_metrics.py` — seed device; POST 3 events to `/ingest`; POST to `/recommendations`; GET `/metrics`; assert Prometheus text format; assert counters `ingest_events_total`, `ingest_quarantine_total`, `recommendation_requests_total`, `recommendation_errors_total`; assert histogram `recommendation_duration_seconds` has buckets

### Implementation for User Story 4

- [X] T056 [US4] Create `src/observability/metrics.py` — define Prometheus metrics: `ingest_events_total` (Counter, labels: protocol, status), `ingest_quarantine_total` (Counter), `recommendation_requests_total` (Counter, labels: provider_count), `recommendation_errors_total` (Counter, labels: reason), `recommendation_duration_seconds` (Histogram, buckets: .1 .25 .5 .75 1.0 2.5), `active_devices_total` (Gauge)
- [X] T057 [US4] Create `src/observability/tracing.py` — OpenTelemetry `TracerProvider` setup; `configure_tracer(service_name)`; `get_tracer()` helper; OTLP exporter config (env-driven, no-op in local dev); add trace-ID-to-structlog binding middleware
- [X] T058 [US4] Update `src/api/routers/ingest.py` — increment `ingest_events_total` (labels: `http`, `accepted`/`quarantined`) after processing; record trace span
- [X] T059 [US4] Update `src/api/routers/recommendations.py` — record start time; increment `recommendation_requests_total`; observe `recommendation_duration_seconds`; increment `recommendation_errors_total` on 503/402; record trace span
- [X] T060 [US4] Create `src/api/routers/health.py` — `GET /health` (200 JSON with db/redis status); `GET /metrics` (Prometheus `generate_latest()` with `text/plain` content type)
- [X] T061 [US4] Update `src/api/main.py` — mount `health_router`; add `PrometheusMiddleware` (request count + latency per path); call `configure_tracer("health-platform")`
- [X] T062 [US4] Create `infra/grafana/provisioning/datasources/prometheus.yaml` — Prometheus datasource pointing to `http://prometheus:9090`
- [X] T063 [US4] Create `infra/grafana/provisioning/dashboards/health-platform.json` — Grafana dashboard with panels: Ingest Throughput (rate), Quarantine Rate, Recommendation Latency (p50/p95 histogram), Error Rate, Active Devices, Provider Success Rate
- [X] T064 [US4] Update `docker-compose.yml` — add `prometheus` service (prom/prometheus:v2.51, scrape config for app `/metrics`); add `grafana` service (grafana/grafana:10, provisioning volumes mounted, port 3000)

**Checkpoint**: `make test-integration` passes for T055. `make dev` + `open localhost:3000` shows Grafana dashboard with live panels. US4 independently verifiable. All prior tests still pass.

---

## Phase 7: Infrastructure, Async Transport & Polish

**Purpose**: CloudFormation stacks, bootstrap script, async MQTT consumer, third provider,
data seeding, and quickstart validation. These tasks may proceed in parallel once US1–US4 are
stable.

- [X] T065 [P] Create `infra/cloudformation/networking.yaml` — VPC, 2 public + 2 private subnets, Internet Gateway, NAT Gateway (single-AZ for PoC), route tables, security groups (ALB-SG, ECS-SG, RDS-SG, Redis-SG)
- [X] T066 [P] Create `infra/cloudformation/iam.yaml` — ECS task execution role, ECS task role with inline policies: Kinesis (PutRecord, GetRecords, GetShardIterator, DescribeStream), IoT (CreateThing, DescribeThing, UpdateThingShadow), S3 (PutObject cold archive), Secrets Manager (GetSecretValue)
- [X] T067 [P] Create `infra/cloudformation/iot.yaml` — `AWS::IoT::Policy` (per-device topic-scoped publish/subscribe), `AWS::IoT::TopicRule` (SQL: `SELECT * FROM 'health/telemetry/+'` → Kinesis PutRecord action with IAM role), JITR Lambda function + `AWS::Lambda::Permission` for IoT trigger; Lambda code: `UpdateCertificate(ACTIVE)` + `CreateThing` + `AttachThingPrincipal`
- [X] T068 [P] Create `infra/cloudformation/streaming.yaml` — `AWS::Kinesis::Stream` (2 shards, 24 h retention), export stream name + ARN for cross-stack reference
- [X] T069 Create `infra/cloudformation/compute.yaml` — `AWS::ECR::Repository`, `AWS::ECS::Cluster`, `AWS::ECS::TaskDefinition` (0.5 vCPU / 1 GB, task role from iam.yaml, env vars from Secrets Manager), `AWS::ECS::Service` (desired 1, ALB target group), `AWS::ElasticLoadBalancingV2::*` (ALB, listener HTTPS/443, target group), `AWS::RDS::DBInstance` (postgres15, db.t3.micro, single-AZ, encrypted), `AWS::ElastiCache::ReplicationGroup` (Redis 7, cache.t3.micro)
- [X] T070 [P] Create `infra/cloudformation/observability.yaml` — ECS task definitions + services for Prometheus and Grafana; CloudWatch log groups for app + infra services; ALB listener rules routing `/grafana` prefix to Grafana target group
- [X] T071 Create `infra/cloudformation/root.yaml` — `AWS::CloudFormation::Stack` resources for all 6 nested stacks in dependency order; pass cross-stack outputs as parameters (VPC ID, subnet IDs, security group IDs, Kinesis stream name, RDS endpoint)
- [X] T072 Create `infra/bootstrap.sh` — validate prerequisites (aws-cli, docker, jq); create S3 bucket for templates; upload all CloudFormation YAML files; deploy stacks in order (networking → iam → iot+streaming parallel → compute → observability); wait for each stack; register CA certificate with `aws iot register-ca-certificate`; create IoT policy; run seed script against deployed ALB endpoint; print summary (ALB URL, Grafana URL, IoT endpoint)
- [X] T073 Create `src/ingestion/adapters/mqtt_consumer.py` — `MqttKinesisConsumer`; connects to Mosquitto (local) or AWS IoT Core MQTT (prod) via `aiomqtt`; subscribes to `health/telemetry/+`; on message: parse payload → `IngestionEvent` → validate → publish to Kinesis/Redis Streams
- [X] T074 Create `src/stream_consumer/consumer.py` — `KinesisConsumer`; registered as FastAPI lifespan background task; polls Kinesis GetRecords via `asyncio.to_thread` every 200 ms; deserialises events; routes by partition key to appropriate domain handler (telemetry → validator + publish chain)
- [X] T075 [P] Create `src/recommendation/adapters/service3_adapter.py` — `Service3Adapter(ProviderAdapter)`; endpoint + token from `SERVICE3_ENDPOINT` / `SERVICE3_API_TOKEN` env vars; schema selected by `SERVICE3_SCHEMA` env var (delegates to service1 or service2 parsing logic via strategy pattern)
- [X] T076 [P] Create `tests/contract/test_service3_contract.py` — contract test for third provider endpoint (skipped if `SERVICE3_ENDPOINT` not set); asserts response schema matches selected schema type
- [X] T077 [P] Create `scripts/seed.py` — CLI script: generates 10 device profiles (mixed types, plausible height/weight from simulator seed profiles); POSTs to `/api/v1/devices` for each; prints device IDs; invoked by `make seed`
- [X] T078 Update `docker-compose.yml` — verify `app` service mounts port 9000 for ingest alongside port 8000 for API; add `MQTT_BROKER_URL=mqtt://mosquitto:1883` env var for local dev; add `SEED_DEVICE_COUNT=10` env var
- [X] T079 Run `quickstart.md` validation — `make dev && make seed && make test` must all succeed; open localhost:3000 and verify dashboard panels are populated; document any deviations from quickstart.md steps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2/US3/US4
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1/US3/US4 (uses pre-seeded device for own tests)
- **US3 (Phase 5)**: Depends on Phase 2 + US1 (recommendations router must exist to integrate credit deduction)
- **US4 (Phase 6)**: Depends on Phase 2 + US1 + US2 (metrics instrument existing routes)
- **Infrastructure (Phase 7)**: Can begin after US1 checkpoint; CloudFormation tasks are independent of story completion

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — independent
- **US2 (P2)**: Can start after Phase 2 — independent (runs in parallel with US1)
- **US3 (P3)**: Depends on US1 recommendation router existing (T033)
- **US4 (P4)**: Depends on US1 and US2 routers existing (T032, T033, T043)

### Within Each Story

1. Tests MUST be written and confirmed failing (Red) before implementation starts
2. `interfaces.py` before adapters (all stories)
3. Domain logic (validator, aggregator, ledger, tier_engine) before routers
4. Routers before `main.py` mount updates
5. `dependencies.py` updates alongside or after router creation

### Parallel Opportunities

```bash
# Phase 1: Run in parallel
T003 (Dockerfile) || T004 (.env.example)

# Phase 2: Run in parallel once T005-T006 done
T007 (Device model) || T008 (remaining models)
T009 (Alembic) depends on T007+T008 completing first

# Phase 3 tests: All parallel (different files)
T015 || T016 || T017 || T018 || T019 || T020 || T021

# Phase 3 implementation: Parallel after T022
T027 (service1 adapter) || T028 (service2 adapter)  # after T026

# Phase 4: Parallel with Phase 3 after Phase 2 checkpoint
T037 || T038  # tests
T040 || T041 || T042  # adapters (after T039)

# Phase 7: All CloudFormation tasks parallel
T065 || T066 || T067 || T068  # then T069, then T070, then T071
T073 || T074 || T075 || T077  # independent of CloudFormation
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all)
3. Complete Phase 3: US1 (ingest + recommendations end-to-end)
4. **STOP and VALIDATE**: `POST /ingest` → `POST /recommendations` returns grouped results in < 1 s
5. Demo-able at this point — core value proposition proven

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready
2. Phase 3 (US1) → Ingest + Recommendations working → **MVP demo**
3. Phase 4 (US2) → Device registration + IoT twin live → **Demo extended**
4. Phase 5 (US3) → Credits + tiers active → **Business logic complete**
5. Phase 6 (US4) → Grafana dashboard → **Full PoC demo-ready**
6. Phase 7 → AWS CloudFormation → **Production-deployable**

### Solo-Developer Notes

- Tackle CloudFormation tasks (T065–T072) after US1 is working — it unlocks AWS testing without
  blocking local development
- `make test-contract` requires internet access to hit live provider endpoints — run separately
  from `make test-unit` and `make test-integration` which are fully local
- Use `LOCAL_DEV=true` (default in `.env.example`) for all local work — no AWS credentials needed
  until Phase 7

---

## Notes

- `[P]` tasks = different files, no incomplete-task dependencies — safe to run in parallel
- `[US*]` label maps each task to its user story for traceability
- Constitution Principle II is enforced: every test task precedes its implementation task
- Confirm Red → Green for each story before moving to the next
- Commit after each phase checkpoint (`make test` green)
- `docker-compose.test.yml` (created as part of T013 or as a variation) is used by
  `make test-integration` to spin up a clean DB and Redis for each test run
