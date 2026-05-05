# Research: Health Intelligence Platform PoC

**Branch**: `001-health-intelligence-poc` | **Date**: 2026-05-04

## Decision 1: Stream Processing — AWS Kinesis Data Streams

**Decision**: Single AWS Kinesis Data Stream; telemetry, recommendation-trigger, and credit
events differentiated by partition key. Two shards for PoC (supports ~2 MB/s write throughput).

**Rationale**: Managed service — zero cluster operations for a sole maintainer. Native ECS IAM
role integration eliminates credential management. Aligns with user's explicit AWS-first choice.
Kinesis replay window (24 h default) satisfies the offline-sync stale-event detection requirement.

**Alternatives considered**:
- Apache Kafka: operationally heavy (ZooKeeper/KRaft + broker management); disproportionate for
  a single-operator PoC. Best alternative for future multi-team production migration.
- Redis Streams: lightweight, viable; but adds a separate Redis cluster to manage and is less
  realistic at the platform's stated 14.4 TB/day production scale.
- AWS SQS FIFO: no replay, no consumer group semantics needed for PoC; rejected.

---

## Decision 2: IoT Core Integration — JITR Mode

**Decision**: Platform registers the CA certificate + IoT policy + topic rule + JITR Lambda.
Devices auto-register on first MQTT connect (JITR flow). `AWS_IOT_REGISTRATION_MODE=jitr`
is set in the simulator's environment.

**Key AWS calls (platform / bootstrap)**:
- `RegisterCACertificate` (one-time, via bootstrap.sh)
- `CreatePolicy` — per-device topic-scoped policy template
  (`topicfilter/health/telemetry/${iot:Connection.Thing.ThingName}`)
- `CreateTopicRule` — routes `health/telemetry/+` events to the Kinesis stream
- JITR Lambda (CloudFormation): triggered by `$aws/events/certificates/registered/+`,
  calls `UpdateCertificate(ACTIVE)` + `CreateThing` + `AttachThingPrincipal`

**MQTT topic pattern**: `health/telemetry/{device_id}` (device_id = certificate CN)

**Rationale**: Simulator already implements the JITR client-side flow
(`CERT_APPROVAL_DELAY_SECONDS=5` reconnect loop). Platform-side setup is entirely declarative
(CloudFormation + one-time bootstrap) — no per-device provisioning calls needed from the API.

**Alternatives considered**:
- Direct registration mode: requires the platform to call `RegisterCertificateWithoutCA`
  per device — couples provisioning to the API and doesn't scale.
- AWS IoT Fleet Provisioning: more powerful but requires Provisioning Template; overkill for PoC.

---

## Decision 3: Recommendation Provider Fan-Out — asyncio.gather with Timeout

**Decision**: `asyncio.gather(*[p.get(request) for p in providers], return_exceptions=True)`
with an 800 ms overall timeout. Partial results are returned when one provider times out or
errors; the error is logged with trace ID and provider ID.

**Implementation pattern** (from simulator research):
```python
results = await asyncio.wait_for(
    asyncio.gather(*tasks, return_exceptions=True),
    timeout=0.8
)
```

**Rationale**: Eliminates sequential latency accumulation. `return_exceptions=True` matches the
simulator's proven pattern for resilient fan-out. 800 ms leaves 200 ms for DB profile lookup,
response serialisation, and network RTT — sufficient margin for the <1 s SLA.

**Alternatives considered**:
- Sequential calls: violates Constitution Principle IV (Real-Time Performance) — rejected.
- Per-provider individual timeouts + gather: more granular but adds complexity; consider
  post-PoC if provider SLA divergence is observed.

---

## Decision 4: Kinesis Consumer — asyncio Background Task

**Decision**: Single asyncio background task registered in FastAPI `lifespan`, using
`asyncio.to_thread(boto3_client.get_records, ...)` to avoid blocking the event loop.

**Implementation pattern** (from simulator research):
```python
await asyncio.to_thread(_blocking_kinesis_get_records, shard_iter)
```

**Rationale**: Keeps the architecture as a single deployable unit (one ECS task). For PoC
throughput (10–100 devices), polling every 200 ms is sufficient. Shard iterator is refreshed
after each batch; `GetShardIterator` is called on startup.

**Alternatives considered**:
- Separate consumer ECS service: adds a second task definition, second ECR image build, more
  CloudFormation resources — unnecessary for a single-operator PoC.
- AWS Lambda event-source mapping on Kinesis: viable for production; adds Lambda to the
  architecture; rejected to keep PoC footprint minimal.

---

## Decision 5: Local Development — Docker Compose with Mock Adapters

**Decision**: `LOCAL_DEV=true` env flag activates `local_registry_adapter.py` (PostgreSQL twin)
and publishes to Redis Streams instead of Kinesis. Mosquitto handles local MQTT. Grafana +
Prometheus run in the same Compose stack.

**Rationale**: No AWS credentials required for local iteration — every test scenario is
coverable locally. Reduces PoC AWS spend during development. The adapter pattern (Constitution
Principle III) makes swapping trivially safe.

**Alternatives considered**:
- LocalStack: emulates AWS APIs locally; adds a heavy container and is known to be flaky for
  IoT Core. Rejected in favour of purpose-built local adapters.

---

## Decision 6: Compute — ECS Fargate + ALB

**Decision**: Single ECS Fargate service, 0.5 vCPU / 1 GB RAM task definition. ALB with HTTPS
listener (ACM certificate). CloudWatch logging for task stdout.

**Rationale**: User confirmed this choice (clarification Q1). No cold starts; container-native;
integrates natively with IAM task roles for Kinesis and Secrets Manager access.

**Alternatives considered**:
- Lambda + API Gateway: cold-start risk incompatible with <1 s SLA.
- EC2: manual instance lifecycle management; less cloud-native.

---

## Decision 7: Database — RDS PostgreSQL db.t3.micro

**Decision**: RDS PostgreSQL 15 on `db.t3.micro` (single-AZ for PoC).

**Rationale**: Cheapest option (≈ $15/month) appropriate for PoC scale. Easy to upgrade to
`db.t3.small` or Aurora Serverless v2 post-PoC with a CloudFormation parameter change.

**Alternatives considered**:
- Aurora Serverless v2: more expensive, auto-scales, better long-term — recommended migration
  path but overkill for demo scale.
- DynamoDB: no JOIN support; credit ledger and reward tier logic maps better to relational model.

---

## Decision 8: Height/Weight Enrichment

**Decision**: Height (cm) and weight (kg) stored in the `Device` entity at registration time.
The ingestion pipeline's `/ingest` handler loads the device profile from the cache (Redis) or
DB and attaches biometrics to every outgoing recommendation provider call.

**Rationale**: The Device Simulator does not include height/weight in telemetry payloads
(confirmed by inspecting `simulator/backend/app/generators/telemetry.py`). Storing at
registration means biometrics are available for every event without re-transmission.

**Implication for bootstrap seeding**: The `make seed` command must POST device registrations
with plausible height/weight values to match the simulator's `SEED_DEVICE_COUNT` profiles.

---

## Decision 9: TLS Strategy

**Decision**: TLS terminated at ALB (ACM certificate, TLS 1.3) on AWS. Plaintext HTTP within
the VPC (ECS task ↔ RDS / Redis). Local Docker Compose uses HTTP only.

**Rationale**: Per spec assumption — TLS is architecturally documented with a clear upgrade
path. ALB handles TLS termination; no per-service certificate management needed.
Within the private VPC, application-layer encryption is replaced by network isolation (security
groups). This is standard AWS practice for Fargate workloads.
