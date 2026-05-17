# Implementation Plan: Health Intelligence Platform PoC

**Branch**: `001-health-intelligence-poc` | **Date**: 2026-05-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-health-intelligence-poc/spec.md`

## Summary

Build a Python FastAPI ingestion and recommendation platform that receives health telemetry from
the existing Device Simulator (HTTP on port 9000 and MQTT via AWS IoT Core), enriches events
with stored biometric profiles, fans out concurrently to three external recommendation providers,
aggregates and normalises results, tracks per-device credits and reward tiers, and exposes a
Prometheus + Grafana observability stack — all provisioned via six nested AWS CloudFormation
stacks and a single bootstrap shell script operated by one person.

**Single-deployer constraint**: Architecture favours managed AWS services over self-hosted
components to minimise operational burden. Local development runs entirely in Docker Compose
with lightweight mock adapters (no AWS credentials required).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.115, pydantic 2.x, SQLAlchemy 2.0 (async), asyncpg 0.29,
boto3 1.34, httpx 0.27, structlog 24.x, opentelemetry-sdk 1.24, prometheus-client 0.20,
aiomqtt 2.x, alembic 1.13, moto 5.x (test AWS mocks)
**Storage**: PostgreSQL 15 (device registry, telemetry events, credit ledger, quarantine) +
Redis 7 (idempotency keys, short-lived cache) + AWS S3 (cold telemetry archive)
**Testing**: pytest 8 + pytest-asyncio, httpx (async contract tests), moto 5 (AWS service
mocks), pytest-cov for coverage gating
**Target Platform**: AWS ECS Fargate eu-central-1 (AWS deployment) + Docker Compose (local dev)
**Project Type**: Web service (REST API) + asyncio background task (Kinesis consumer)
**Performance Goals**: p95 < 1 s end-to-end for recommendation path; three provider calls
concurrent within 800 ms budget (200 ms headroom for DB enrichment + serialisation)
**Constraints**: Single deployer/maintainer; single-command local startup (`docker compose up`);
PoC scope (10–100 concurrent demo devices); nested CloudFormation; ECS Fargate for compute
**Scale/Scope**: PoC demo (10–100 devices), architecture designed for future 1 M+ DAU

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate condition | Status |
|-----------|----------------|--------|
| I. Modular Architecture (SOLID-First) | Each domain (ingestion, recommendation, digital_twin, credits, observability) in its own module with a public `interfaces.py`; no circular imports; cross-domain calls only via injected interfaces | ✅ PASS |
| II. Test-First Development (NON-NEGOTIABLE) | Unit + integration + contract test files defined before implementation; pytest passes as merge gate | ✅ PASS — test tree pre-defined in project structure |
| III. Protocol-Agnostic Ingestion | `IngestionAdapter` ABC; HTTP and MQTT adapters; adding a third protocol touches only `adapters/`; zero changes to core pipeline | ✅ PASS |
| IV. Real-Time Performance | `asyncio.gather` with 800 ms timeout for concurrent provider fan-out; fully async FastAPI; Kinesis consumer is non-blocking asyncio background task | ✅ PASS |
| V. Security & Compliance by Design | IoT Core X.509 mTLS for devices; ALB ACM TLS termination; secrets in AWS Secrets Manager; PII fields annotated in data model; no secrets in source | ✅ PASS |
| VI. Observability & Data Quality | OpenTelemetry on all request paths; Prometheus metrics endpoint; Grafana in both Docker Compose and ECS; validation + quarantine gate on every inbound event | ✅ PASS |
| VII. Open-Source & Cloud-Native First | All components containerised; IaC via CloudFormation; ⚠️ Kinesis instead of Kafka/Redis Streams — justified in Complexity Tracking | ⚠️ DEVIATION — see below |

**Post-design re-check** (after data-model.md and contracts): re-verify Principles I and III
confirm no domain boundary leakage in API contracts.

## Project Structure

### Documentation (this feature)

```text
specs/001-health-intelligence-poc/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions + PII map
├── quickstart.md        # Phase 1: 15-minute run guide
├── contracts/
│   ├── ingest-api.md
│   ├── devices-api.md
│   └── recommendations-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code (repository root)

```text
src/
├── api/
│   ├── main.py                    # FastAPI app factory, lifespan, middleware, port config
│   ├── dependencies.py            # DI: DB session, adapters, registry, ledger, providers
│   └── routers/
│       ├── ingest.py              # POST /ingest (port 9000) — simulator entry point
│       ├── devices.py             # POST /api/v1/devices, GET /api/v1/devices/{id}
│       ├── recommendations.py     # POST /api/v1/devices/{id}/recommendations
│       └── health.py              # GET /health, GET /metrics (Prometheus)
│
├── ingestion/
│   ├── interfaces.py              # IngestionAdapter ABC + IngestionEvent dataclass
│   ├── adapters/
│   │   ├── http_adapter.py        # Parses simulator HTTP JSON → IngestionEvent
│   │   └── mqtt_consumer.py       # Kinesis GetRecords loop → IngestionEvent (background)
│   ├── validator.py               # Schema validation + anomaly-detection; quarantine on fail
│   └── publisher.py               # Publishes IngestionEvent → Kinesis (or Redis Streams locally)
│
├── recommendation/
│   ├── interfaces.py              # ProviderAdapter ABC + RecommendationResult dataclass
│   ├── adapters/
│   │   ├── service1_adapter.py    # confidence model: POST height/weight, map → score×1000
│   │   ├── service2_adapter.py    # priority model: POST mass(lbs)/height(ft)/birth_date/GUID
│   │   └── service3_adapter.py    # third provider (same interface, distinct env token)
│   ├── aggregator.py              # asyncio.gather fan-out, 800 ms timeout, partial results
│   ├── normalizer.py              # Normalised score, group by short text, max-merge, sort
│   └── models.py                  # AggregatedRecommendation, ProviderError
│
├── digital_twin/
│   ├── interfaces.py              # TwinRegistryAdapter ABC
│   ├── iot_core_adapter.py        # AWS IoT Core: CreateThing + shadow sync + JITR hooks
│   ├── local_registry_adapter.py  # PostgreSQL-backed twin for local dev (no AWS creds)
│   └── registry.py                # Domain logic; delegates to injected TwinRegistryAdapter
│
├── credits/
│   ├── ledger.py                  # Atomic credit deduction (SELECT FOR UPDATE); top-up
│   ├── tier_engine.py             # Tier threshold evaluation: Bronze/Silver/Gold/Platinum
│   └── models.py
│
├── stream_consumer/
│   └── consumer.py                # FastAPI lifespan background task: Kinesis GetRecords loop
│                                  # (asyncio.to_thread for blocking boto3 calls)
│
├── observability/
│   ├── metrics.py                 # Prometheus Counter + Histogram definitions
│   ├── tracing.py                 # OpenTelemetry tracer + correlation-ID propagation
│   └── logging.py                 # structlog JSON renderer + trace-ID binding
│
└── config.py                      # Pydantic BaseSettings; all config from env vars

tests/
├── contract/
│   ├── test_service1_contract.py  # Live contract test: real HTTP call + schema assertion
│   ├── test_service2_contract.py
│   └── test_service3_contract.py
├── integration/
│   ├── test_ingest_http.py        # POST /ingest → DB + Kinesis mock
│   ├── test_recommendation_flow.py # /recommendations → concurrent providers → aggregated result
│   ├── test_device_registration.py # Register device → twin created → credits initialised
│   └── test_credits_tier.py       # Credit deduction → tier transition assertions
└── unit/
    ├── test_aggregator.py
    ├── test_normalizer.py
    ├── test_validator.py
    ├── test_ledger.py
    └── test_tier_engine.py

infra/
├── cloudformation/
│   ├── root.yaml                  # Root stack: links all nested stacks, passes outputs
│   ├── networking.yaml            # VPC, public/private subnets, NAT GW, SGs, IGW
│   ├── iam.yaml                   # ECS task role + Kinesis/IoT/S3/SecretsManager policies
│   ├── iot.yaml                   # IoT policy, topic rule (→ Kinesis), JITR Lambda
│   ├── streaming.yaml             # Kinesis Data Stream (2 shards for PoC)
│   ├── compute.yaml               # ECR repo, ECS cluster/service/task, ALB, RDS, Redis
│   └── observability.yaml         # Grafana + Prometheus ECS services, CW log groups
├── grafana/
│   └── provisioning/
│       ├── datasources/prometheus.yaml
│       └── dashboards/health-platform.json
└── bootstrap.sh                   # Single-operator deploy: stacks → CA registration → seed

docker-compose.yml                 # Full local stack (app + postgres + redis + mosquitto
                                   #   + prometheus + grafana)
docker-compose.test.yml            # Integration test environment
Dockerfile
Makefile                           # make dev | make test | make deploy | make seed | make lint
pyproject.toml
.env.example
```

**Structure decision**: Single-project layout under `src/` with SOLID domain modules. The FastAPI
`api/` layer depends only on domain `interfaces.py` ABCs (DIP); concrete adapters are injected
via `dependencies.py`. The `digital_twin` module ships two adapter implementations so local
development requires zero AWS credentials. Infrastructure lives entirely under `infra/` and is
never imported by application code.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| AWS Kinesis instead of Kafka or Redis Streams (Constitution §VII stack constraint) | User explicitly chose Kinesis in the clarification session for AWS alignment; managed service eliminates cluster operations for a sole operator | Kafka: requires ZooKeeper/KRaft cluster — disproportionate ops overhead for one person. Redis Streams: valid technically but user's stated preference was AWS-native; also Kinesis is more realistic at 14.4 TB/day scale. Justified by single-deployer constraint and Principle VII's "cloud-native first" intent |
| Two TwinRegistry adapter implementations (IoT Core + local PostgreSQL) | Local dev must work without AWS credentials; IoT Core is used on AWS | A single IoT Core adapter would require every developer to provision cloud resources for any local test run, violating the single-command startup requirement (Constitution §PoC Delivery Standards) |
