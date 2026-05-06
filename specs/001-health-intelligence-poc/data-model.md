# Data Model: Health Intelligence Platform PoC

**Branch**: `001-health-intelligence-poc` | **Date**: 2026-05-04

> **PII annotation key**: Fields marked `[PII]` contain Personal Health Information subject to
> HIPAA / GDPR. These fields MUST be encrypted at rest (RDS AES-256 storage encryption) and
> MUST NOT appear in logs, metrics labels, or error messages.

---

## Entity 1: Device

**Storage**: PostgreSQL table `devices`
**Purpose**: Canonical device identity, biometric profile (for provider enrichment), credit
balance, reward tier, and link to the AWS IoT Core thing name.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | Internal device identity |
| `device_type` | ENUM | NOT NULL | `smartwatch` \| `fitness_tracker` \| `smartphone` \| `laptop` |
| `model` | VARCHAR(128) | NOT NULL | Hardware model string from simulator |
| `firmware_version` | VARCHAR(64) | NOT NULL | e.g. `2.2.3` |
| `os` | VARCHAR(64) | NOT NULL | e.g. `WearOS 3.2` |
| `user_id` | UUID | NOT NULL `[PII]` | Logical user owning this device |
| `height_cm` | NUMERIC(5,1) | NOT NULL `[PII]` | Stored at registration; used to enrich provider calls |
| `weight_kg` | NUMERIC(5,2) | NOT NULL `[PII]` | Stored at registration; used to enrich provider calls |
| `credit_balance` | INTEGER | NOT NULL, default 0, CHECK >= 0 | Current spendable credits |
| `reward_tier` | ENUM | NOT NULL, default `bronze` | `bronze` \| `silver` \| `gold` \| `platinum` |
| `cumulative_credits_spent` | INTEGER | NOT NULL, default 0 | Used for tier threshold evaluation |
| `iot_thing_name` | VARCHAR(128) | UNIQUE, nullable | AWS IoT Core thing name (null until JITR activates) |
| `registered_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | Updated via trigger |

**Reward tier thresholds** (cumulative_credits_spent):

| Tier | Min credits spent | Max credits spent |
|------|------------------|------------------|
| Bronze | 0 | 999 |
| Silver | 1,000 | 4,999 |
| Gold | 5,000 | 19,999 |
| Platinum | 20,000 | ∞ |

**State transitions**: `bronze → silver → gold → platinum` (monotonic — tiers never decrease).
Tier is recomputed by `tier_engine.py` on every credit deduction.

---

## Entity 2: TelemetryEvent

**Storage**: PostgreSQL table `telemetry_events` (hot, 7-day retention) + AWS S3 (cold archive,
Parquet, partitioned by `device_id/year/month/day`)
**Purpose**: Record of every inbound health metric event from the simulator.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | Internal record ID |
| `event_id` | VARCHAR(128) | UNIQUE NOT NULL | Simulator-generated event UUID (idempotency key) |
| `device_id` | UUID | FK → devices.id NOT NULL | |
| `source_protocol` | ENUM | NOT NULL | `http` \| `mqtt` |
| `received_at` | TIMESTAMPTZ | NOT NULL, default now() | Server ingestion timestamp |
| `event_timestamp` | TIMESTAMPTZ | NOT NULL | Simulator-provided timestamp |
| `is_stale` | BOOLEAN | NOT NULL, default false | True if event_timestamp > 24 h before received_at |
| `is_anomaly` | BOOLEAN | NOT NULL, default false | From simulator's `is_anomaly` flag |
| `validation_status` | ENUM | NOT NULL | `valid` \| `invalid` \| `stale` |
| `payload` | JSONB | NOT NULL | Full simulator payload (heart_rate, spo2, steps, etc.) |
| `trace_id` | VARCHAR(64) | NOT NULL | OpenTelemetry trace ID |
| `batch_id` | UUID | FK → ingestion_batches.id, nullable | Set when event arrived in a batch |

**Index**: `(device_id, received_at DESC)` for dashboard queries.

**Note on payload schema**: The `payload` JSONB stores the full simulator event. The fields
`heart_rate.bpm`, `spo2.percentage`, `steps.count`, `gps.latitude/longitude`, `battery_pct`,
`stress.score`, and `hydration.level_percent` are the primary metrics exposed via the
dashboard API. Height/weight are NOT in the payload; they are read from `devices` for enrichment.

---

## Entity 3: IngestionBatch

**Storage**: PostgreSQL table `ingestion_batches`
**Purpose**: Tracks multi-event submissions from offline-sync device sessions.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `device_id` | UUID | FK → devices.id NOT NULL | |
| `batch_id` | VARCHAR(128) | UNIQUE NOT NULL | Simulator-generated batch UUID |
| `event_count` | INTEGER | NOT NULL | Declared count from simulator |
| `received_count` | INTEGER | NOT NULL, default 0 | Processed event count |
| `submitted_at` | TIMESTAMPTZ | NOT NULL | Simulator batch timestamp |
| `processing_status` | ENUM | NOT NULL, default `pending` | `pending` \| `processing` \| `completed` \| `failed` |
| `is_stale` | BOOLEAN | NOT NULL, default false | True if any event is > 24 h old |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

---

## Entity 4: RecommendationRequest

**Storage**: PostgreSQL table `recommendation_requests`
**Purpose**: Audit log of every recommendation aggregation call — which device, which inputs,
which providers responded, and what was returned.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `device_id` | UUID | FK → devices.id NOT NULL | |
| `trace_id` | VARCHAR(64) | NOT NULL | |
| `height_cm` | NUMERIC(5,1) | NOT NULL `[PII]` | Enriched from device profile at call time |
| `weight_kg` | NUMERIC(5,2) | NOT NULL `[PII]` | Enriched from device profile at call time |
| `providers_called` | TEXT[] | NOT NULL | e.g. `['service1','service2','service3']` |
| `providers_succeeded` | TEXT[] | NOT NULL | Subset that responded within timeout |
| `result` | JSONB | nullable | Aggregated AggregatedRecommendation list |
| `requested_at` | TIMESTAMPTZ | NOT NULL | |
| `completed_at` | TIMESTAMPTZ | nullable | Null until aggregation finishes |
| `duration_ms` | INTEGER | nullable | End-to-end duration for latency tracking |

---

## Entity 5: CreditTransaction

**Storage**: PostgreSQL table `credit_transactions`
**Purpose**: Append-only ledger of all credit events (spend and top-up).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `device_id` | UUID | FK → devices.id NOT NULL | |
| `amount` | INTEGER | NOT NULL | Negative = spend; positive = top-up |
| `action_type` | ENUM | NOT NULL | `recommendation` \| `registration_bonus` \| `top_up` |
| `resulting_balance` | INTEGER | NOT NULL, CHECK >= 0 | Balance after this transaction |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Consistency rule**: `devices.credit_balance` is updated atomically with each transaction
using `SELECT FOR UPDATE` on the device row. The `resulting_balance` snapshot enables
balance reconstruction from the ledger without full replay.

---

## Entity 6: QuarantineRecord

**Storage**: PostgreSQL table `quarantine_records`
**Purpose**: Failed validation events — stored with error detail for operator review.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `device_id` | UUID | nullable | May be absent if device_id in payload is invalid |
| `raw_payload` | JSONB | NOT NULL | Original inbound payload |
| `validation_errors` | JSONB | NOT NULL | Array of error objects: `{field, code, message}` |
| `source_protocol` | ENUM | NOT NULL | `http` \| `mqtt` |
| `trace_id` | VARCHAR(64) | NOT NULL | |
| `quarantined_at` | TIMESTAMPTZ | NOT NULL, default now() | |

---

## Value Objects (in-memory only, not persisted as tables)

### IngestionEvent
Canonical internal representation produced by any `IngestionAdapter`:
```
device_id: str
event_id: str
source_protocol: SourceProtocol
event_timestamp: datetime
payload: dict          # Raw simulator payload fields
trace_id: str
is_batch: bool
batch_id: str | None
```

### ProviderResult
Returned by each `ProviderAdapter.get_recommendations()`:
```
provider_id: str       # 'service1' | 'service2' | 'service3'
recommendations: list[RawRecommendation]
error: str | None
duration_ms: int
```

### RawRecommendation
Intermediate normalised form before grouping:
```
short_text: str        # Short recommendation text (group key)
detail: str | None
normalised_score: float  # service1: confidence×1000 | service2: priority (1–1000)
provider_id: str
```

### AggregatedRecommendation
Final response item after grouping and sorting:
```
short_text: str
max_score: float       # Highest normalised_score across all providers for this group
providers: list[str]   # Which providers contributed
detail: str | None     # Detail from the highest-scoring provider
```

---

## PII Data Map

| Entity | PII Fields | Retention | Deletion mechanism |
|--------|------------|-----------|-------------------|
| Device | `user_id`, `height_cm`, `weight_kg` | Until device deregistered | DELETE devices WHERE id = ? |
| TelemetryEvent | `payload` (GPS lat/lon) | 7 days (PostgreSQL) + archive | RDS TTL policy + S3 lifecycle rule |
| RecommendationRequest | `height_cm`, `weight_kg` | 90 days | Scheduled purge job |
| CreditTransaction | None | Indefinite (financial ledger) | — |
| QuarantineRecord | `raw_payload` (may contain PII) | 30 days | Scheduled purge job |

---

## Database Migrations

Managed by **Alembic** with auto-generated revision files under `src/db/migrations/`.
Migration order: `devices` → `ingestion_batches` → `telemetry_events` → `recommendation_requests`
→ `credit_transactions` → `quarantine_records` (FK dependency order).
