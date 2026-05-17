# Implementation Plan: Device Credits Management and Tiered Reward System

**Branch**: `002-credits-reward-system` | **Date**: 2026-05-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-credits-reward-system/spec.md`

## Summary

Extends the existing health platform PoC with a fully configurable credit economy: devices earn credits by submitting health telemetry (with activity-weighted scoring and streak bonuses), spend credits on recommendation services (at tier-discounted rates), and advance through four reward tiers (Bronze → Platinum) as cumulative earnings grow. A React 18/TypeScript/Vite admin frontend provides credit visibility and configuration management. A pre-provisioned Grafana dashboard surfaces credit metrics across the device fleet.

The backend extends the existing Python/FastAPI/PostgreSQL stack. The frontend is the sole React component; the backend remains 100% Python.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5 / Node 20 (React frontend)
**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, structlog, prometheus-client (backend); React 18, Vite 5, TanStack Query v5, shadcn/ui (frontend)
**Storage**: PostgreSQL — new tables `credit_config`; new columns on `devices` and `credit_transactions`
**Testing**: pytest + pytest-asyncio (backend integration/unit); Vitest + React Testing Library (frontend unit)
**Target Platform**: Linux container (Docker Compose), local macOS dev
**Project Type**: Web service (FastAPI) + React SPA admin UI
**Performance Goals**: Credit award latency < 50ms added to ingest path; credit config PUT takes effect within 10 seconds (FR-004)
**Constraints**: Tier computation is O(1) per event; no full-table scans in the hot ingest path
**Scale/Scope**: PoC — up to 10,000 devices; Grafana metrics with per-device labels are acceptable at this scale

## Constitution Check

*GATE: All principles verified. No violations.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture (SOLID-First) | ✅ PASS | Credits domain isolated in `src/credits/`. EarningService, ConfigService, TierEngine each have single responsibility. Ingest router depends on EarningService interface, not implementation. |
| II. Test-First Development | ✅ PASS | Unit tests for EarningService (earning calc, streak logic, multiplier), TierEngine (threshold transitions). Integration tests for all 5 new API endpoints. Contract tests for credits-api.md responses. |
| III. Protocol-Agnostic Ingestion | ✅ PASS | EarningService consumes the existing `IngestionEvent` model — protocol-neutral by construction. MQTT events go through the same earning path as HTTP events. |
| IV. Real-Time Performance | ✅ PASS | Earning is async, runs within the same DB transaction as event persistence. No blocking I/O added. Config loaded once from DB with minimal overhead. |
| V. Security & Compliance by Design | ✅ PASS | All new endpoints require X-API-Key. `CreditConfig.created_by` stores anonymised key hash. No PII in transaction log (device_id is not PII). |
| VI. Observability & Data Quality | ✅ PASS | New Prometheus Gauges for credit metrics. All earning/spending events emit structured logs with trace_id. |
| VII. Open-Source & Cloud-Native First | ✅ PASS | React/Vite/nginx are all open-source. Frontend Docker image is nginx-based. No new proprietary SaaS. |

**Justified deviation**: React 18/TypeScript frontend deviates from the "Python primary" constraint. Justified by: (a) the spec explicitly requires React.js; (b) the constitution permits "other runtimes for edge/device SDKs" — extended here to include the admin UI layer since the backend remains exclusively Python; (c) no backend logic moves to JavaScript.

## Project Structure

### Documentation (this feature)

```text
specs/002-credits-reward-system/
├── plan.md              ← this file
├── research.md          ← Phase 0 decisions
├── data-model.md        ← Phase 1 entities
├── quickstart.md        ← Phase 1 integration guide
├── contracts/
│   └── credits-api.md   ← Phase 1 API contracts
└── tasks.md             ← Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code

```text
# Backend (Python — extends existing src/)
src/
├── credits/
│   ├── __init__.py
│   ├── models.py             # extend CreditActionType enum
│   ├── tier_engine.py        # extend: load thresholds from CreditConfig, apply multipliers
│   ├── ledger.py             # extend: write CreditTransaction rows with reason + metadata
│   ├── earning_service.py    # NEW: award credits for activities + streak tracking
│   └── config_service.py     # NEW: read/write CreditConfig to/from DB
├── db/
│   └── models/
│       ├── credit_config.py  # NEW: CreditConfig ORM model
│       └── credits.py        # extend CreditTransaction: add reason, metadata columns
│   └── migrations/versions/
│       └── 002_credits_extended.py  # NEW: Alembic migration
├── api/
│   └── routers/
│       ├── credit_config.py  # NEW: GET/PUT /api/v1/credit-config
│       └── devices.py        # extend: GET /api/v1/devices/{id}/credits
│                             #         GET /api/v1/devices/{id}/credits/transactions
│                             #         POST /api/v1/devices/{id}/credits (add reason)
│       └── ingest.py         # extend: call EarningService after event persisted
│       └── recommendations.py # extend: apply tier discount, use config cost per service
├── observability/
│   └── metrics.py            # extend: credit Gauge metrics
└── config.py                 # retain initial_credit_balance as bootstrap fallback

# Frontend (React/TypeScript — new)
frontend/
├── src/
│   ├── api/
│   │   └── creditApi.ts          # typed API client (fetch wrappers)
│   ├── components/
│   │   ├── TierBadge.tsx         # coloured badge for Bronze/Silver/Gold/Platinum
│   │   ├── TierProgressBar.tsx   # progress toward next tier
│   │   └── TransactionTable.tsx  # paginated transaction history
│   ├── pages/
│   │   ├── DeviceCreditsPage.tsx # search by device_id, show balance/tier/history
│   │   └── AdminConfigPage.tsx   # edit CreditConfig form
│   ├── App.tsx                   # router, API key context
│   └── main.tsx
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts               # proxy /api → http://localhost:8100
└── Dockerfile                   # multi-stage: node build → nginx serve

# Infra additions
infra/grafana/provisioning/dashboards/
└── credits.json                 # NEW: 6-panel credits Grafana dashboard

docker-compose.yml               # extend: add frontend service (port 3200)
Makefile                         # extend: test-frontend, frontend-dev targets
```

**Structure Decision**: Single repository (monorepo-lite). Backend extends the existing `src/` tree. Frontend lives in a new top-level `frontend/` directory to maintain clear separation. Sharing one docker-compose keeps the local dev experience to `make up`.

## Complexity Tracking

No constitution violations requiring justification. See the React deviation note in the Constitution Check table above.

---

## Phase 0 Summary (Research — complete)

See [research.md](research.md) for full decisions. Key resolved questions:

1. **Frontend tech**: React 18 + TypeScript + Vite → justified, spec-mandated
2. **CreditConfig storage**: PostgreSQL table, single active row, versioned → hot-reloadable (FR-004)
3. **Activity earning hook**: `EarningService` called from ingest router, same DB transaction → atomic + sub-50ms
4. **Streak tracking**: `streak_days` + `last_activity_date` on Device → O(1) update, no joins
5. **Tier basis**: `cumulative_credits_earned` (not spent) → matches spec FR-015; new column added
6. **Transaction schema**: extend with `reason: str` + `metadata: JSONB` → full audit trail (FR-010)
7. **Prometheus metrics**: push-on-write Gauges per device → no DB scan on scrape at PoC scale
8. **Grafana dashboard**: provisioned via JSON → zero-click setup on `docker compose up`

## Phase 1 Summary (Design — complete)

See [data-model.md](data-model.md), [contracts/credits-api.md](contracts/credits-api.md), [quickstart.md](quickstart.md).

**New DB schema additions**:
- `credit_config` table (see data-model.md)
- `devices.streak_days`, `devices.last_activity_date`, `devices.cumulative_credits_earned` columns
- `credit_transactions.reason`, `credit_transactions.metadata` columns
- `CreditActionType` enum extended with: `activity_reward`, `streak_bonus`, `adjustment`, `tier_discount`

**New API endpoints** (see contracts/credits-api.md):
- `GET  /api/v1/credit-config`
- `PUT  /api/v1/credit-config`
- `GET  /api/v1/devices/{id}/credits`
- `GET  /api/v1/devices/{id}/credits/transactions`
- Extend `POST /api/v1/devices/{id}/credits` with `reason` field

**Frontend pages**:
- `DeviceCreditsPage` — device ID search, balance/tier/streak/progress, transaction history
- `AdminConfigPage` — full CreditConfig form with validation

**Grafana dashboard** — 6 panels: credits balance ranking, earned vs spent time series, tier distribution pie, top spenders 24h, streak leaderboard, activity type breakdown
