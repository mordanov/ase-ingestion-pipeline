# Tasks: Device Credits Management and Tiered Reward System

**Input**: Design documents from `specs/002-credits-reward-system/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/credits-api.md ✅ quickstart.md ✅

**Tests**: Included — Constitution Principle II (TDD) is MANDATORY for all implementation work.

**Organization**: Tasks grouped by user story for independent implementation and testing.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold React frontend, add migration file, extend docker-compose and Makefile. No user story work until Phase 2 is done.

- [X] T001 Initialise React frontend: create `frontend/package.json` (react 18, typescript, vite 5, tanstack-query, shadcn-ui), `frontend/tsconfig.json`, `frontend/vite.config.ts` (proxy `/api` → `http://localhost:8100`), `frontend/index.html`
- [X] T002 [P] Create `frontend/Dockerfile` (multi-stage: `node:20-alpine` build → `nginx:alpine` serve static build)
- [X] T003 [P] Add `frontend` service to `docker-compose.yml` on port 3200, mounting nginx config; add `frontend/nginx.conf`
- [X] T004 [P] Add Makefile targets: `frontend-dev` (Vite hot-reload on port 5173), `test-frontend` (`npm run test`), `build-frontend` (`npm run build`)
- [X] T005 Create Alembic migration `src/db/migrations/versions/002_credits_extended.py` with `upgrade()` that: (a) adds `streak_days`, `last_activity_date`, `cumulative_credits_earned` columns to `devices`; (b) creates `credit_config` table; (c) adds `reason VARCHAR(256)` and `metadata JSONB` columns to `credit_transactions`; (d) extends `creditactiontype` enum with `activity_reward`, `streak_bonus`, `adjustment`, `tier_discount`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core ORM models, enum extensions, and DB migration that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 Create `src/db/models/credit_config.py` — `CreditConfig` ORM model with fields: `id UUID PK`, `version INT`, `is_active BOOL`, `default_initial_balance INT`, `activity_earning_rules JSONB`, `service_costs JSONB`, `streak_bonus_7d INT`, `streak_bonus_30d INT`, `tier_thresholds JSONB`, `tier_multipliers JSONB`, `tier_discounts JSONB`, `created_at TIMESTAMPTZ`, `created_by VARCHAR(128)`
- [X] T007 [P] Extend `src/db/models/credits.py` — add `reason: Mapped[str]` (VARCHAR 256, nullable=False, default=""), `metadata: Mapped[dict | None]` (JSONB, nullable=True) to `CreditTransaction`; extend `CreditActionType` enum with `activity_reward`, `streak_bonus`, `adjustment`, `tier_discount`
- [X] T008 [P] Extend `src/db/models/device.py` — add `streak_days: Mapped[int]` (default 0), `last_activity_date: Mapped[date | None]` (nullable), `cumulative_credits_earned: Mapped[int]` (default 0) to `Device`
- [X] T009 Update `src/db/models/__init__.py` to export `CreditConfig` from `credit_config.py`
- [X] T010 Run migration `make migrate` locally and verify schema; update `src/credits/models.py` to re-export `CreditActionType` updated values

**Checkpoint**: DB schema ready — all new tables and columns exist. Confirm with `make migrate` passing and `make test` still showing 51 passed.

---

## Phase 3: User Story 1 — Credit Configuration Management (Priority: P1) 🎯 MVP

**Goal**: Admin can read and update the active credit configuration at runtime with no restart. New device registration uses `default_initial_balance` from config. Recommendation cost comes from `service_costs` map.

**Independent Test**: `GET /api/v1/credit-config` returns default config; `PUT` updates it and `GET` reflects new values; a device registered after a config change starts with the new `default_initial_balance`.

### Tests for User Story 1 (TDD — write first, confirm they fail, then implement)

- [X] T011 [P] [US1] Write integration tests for config CRUD in `tests/integration/test_credits_config.py`: test GET returns 200 with expected shape; test PUT replaces config and GET reflects change; test PUT with invalid service cost (0) returns 422; test PUT with non-ascending tier thresholds returns 422
- [X] T012 [P] [US1] Write integration test that device registered after config change gets updated `default_initial_balance` in `tests/integration/test_credits_config.py`

### Implementation for User Story 1

- [X] T013 [US1] Implement `ConfigService` in `src/credits/config_service.py` — async methods: `get_active() -> CreditConfig`, `create_new_version(data: dict) -> CreditConfig` (deactivates current, inserts new with incremented version), `seed_default_if_missing()` (idempotent bootstrap)
- [X] T014 [US1] Implement `CreditConfigRequest` / `CreditConfigResponse` Pydantic models and validation (service costs ≥ 1, earning rules ≥ 0, tier thresholds ascending, multipliers ≥ 1.0, discounts in [0.0,1.0)) in `src/api/routers/credit_config.py`
- [X] T015 [US1] Implement `GET /api/v1/credit-config` and `PUT /api/v1/credit-config` endpoints in `src/api/routers/credit_config.py` using `ConfigService`; require `X-API-Key`
- [X] T016 [US1] Register `credit_config` router in `src/api/main.py` (`app.include_router(credit_config.router)`)
- [X] T017 [US1] Seed default `CreditConfig` row in app startup lifespan in `src/api/main.py` by calling `await config_service.seed_default_if_missing()`
- [X] T018 [US1] Update `src/api/routers/devices.py` `register_device` to load `default_initial_balance` from `ConfigService.get_active()` instead of `settings.initial_credit_balance`
- [X] T019 [US1] Update `src/api/routers/recommendations.py` to load `service_costs` from `ConfigService.get_active()` and use `config.service_costs.get("service1", config.service_costs.get("default", 1))` for deduction amount; log `credit_cost` in structured log

**Checkpoint**: `GET /api/v1/credit-config` returns active config; `PUT` changes are reflected immediately; new devices get configurable initial balance; recommendation deduction uses configured cost.

---

## Phase 4: User Story 2 — Earning Credits Through Health Activities (Priority: P1)

**Goal**: Telemetry events automatically award credits to devices based on activity scenario, with tier multipliers and streak bonuses. All earning is transactional with a full audit trail.

**Independent Test**: Ingest a `workout` event → device balance increases by `config.activity_earning_rules["workout"] × tier_multiplier`; ingest same `event_id` again → no double-award; ingest 7 consecutive days → streak bonus credited.

### Tests for User Story 2 (TDD — write first, confirm they fail, then implement)

- [X] T020 [P] [US2] Write unit tests for `EarningService` in `tests/unit/test_earning_service.py`: test base earning by scenario, test tier multiplier applied (bronze 1.0, silver 1.25), test streak increment on new-day event, test streak reset on gap > 1 day, test 7-day bonus awarded exactly once, test duplicate event_id returns 0 (no award)
- [X] T021 [P] [US2] Write integration tests for activity earning in `tests/integration/test_activity_earning.py`: test ingest workout event → balance increases; test ingest sleep event → balance increases by smaller amount; test duplicate event_id → balance unchanged on second ingest; test transaction log contains `activity_reward` entry with correct `reason`

### Implementation for User Story 2

- [X] T022 [US2] Extend `src/credits/tier_engine.py` — add `get_multiplier(tier: RewardTier, config: CreditConfig) -> float` and `compute_tier_from_config(cumulative_earned: int, config: CreditConfig) -> RewardTier` (loads thresholds from config JSONB)
- [X] T023 [US2] Extend `src/credits/ledger.py` — add `async def record_transaction(session, device_id, amount, action_type, reason, resulting_balance, metadata=None)` that writes `CreditTransaction` row with all fields; add `async def update_device_balance(session, device, delta, action_type, reason, metadata=None)` that atomically updates `credit_balance`, `cumulative_credits_earned`/`cumulative_credits_spent`, emits Prometheus metric update, and calls `record_transaction`
- [X] T024 [US2] Implement `EarningService` in `src/credits/earning_service.py` — `async def award_for_event(event: IngestionEvent, device: Device, session: AsyncSession) -> int`: loads active config, looks up base amount by `event.scenario`, applies tier multiplier, checks event_id not already in `credit_transactions` (deduplication), calls `ledger.update_device_balance`, updates streak fields, checks streak milestones, awards streak bonus if milestone crossed; returns total awarded (0 if duplicate)
- [X] T025 [US2] Hook `EarningService.award_for_event` into `src/api/routers/ingest.py` — call after `db.add(te)` (telemetry event added) but before final `db.commit()`, pass `event`, `device` (loaded from DB in validator), and `db`; log `credits_awarded` with amount
- [X] T026 [US2] Add credit Prometheus metrics to `src/observability/metrics.py`: `DEVICE_CREDIT_BALANCE = Gauge("device_credit_balance", "Current credit balance", ["device_id"])`, `DEVICE_CREDITS_EARNED = Counter("device_credits_earned_total", "Cumulative earned", ["device_id"])`, `DEVICE_CREDITS_SPENT = Counter("device_credits_spent_total", "Cumulative spent", ["device_id"])`, `DEVICE_STREAK_DAYS = Gauge("device_streak_days", "Current streak", ["device_id"])`, `CREDIT_TIER_TOTAL = Gauge("credit_tier_total", "Devices per tier", ["tier"])`
- [X] T027 [US2] Update `src/credits/ledger.py` `update_device_balance` to call the new Prometheus metric setters after each balance change; update `src/api/routers/recommendations.py` to update `DEVICE_CREDITS_SPENT` and `CREDIT_TIER_TOTAL` after deduction and tier recompute

**Checkpoint**: Ingest a workout event via `curl`, check device balance increased, check `GET /api/v1/devices/{id}/credits/transactions` shows `activity_reward` entry (endpoint from US3 phase can be tested manually).

---

## Phase 5: User Story 3 — Credit Balance and Tier Visibility (Priority: P2)

**Goal**: React web frontend lets users look up any device's credit balance, tier, streak, progress to next tier, and paginated transaction history. Admin can manually top up with a reason.

**Independent Test**: Open `http://localhost:3200`, enter a device ID, see balance/tier badge/progress bar and transaction table populated from live API.

### Tests for User Story 3 (TDD — write first, confirm they fail, then implement)

- [X] T028 [P] [US3] Write integration tests for new device credit endpoints in `tests/integration/test_device_credits_api.py`: test `GET /api/v1/devices/{id}/credits` returns balance, tier, streak, next_tier, credits_to_next_tier; test `GET /api/v1/devices/{id}/credits/transactions` returns paginated list; test `GET` with unknown device returns 404; test `POST /api/v1/devices/{id}/credits` with reason field stores reason in transaction log
- [X] T029 [P] [US3] Write Vitest unit tests for `TierBadge` and `TierProgressBar` components in `frontend/src/components/__tests__/TierBadge.test.tsx` and `TierProgressBar.test.tsx` — verify correct colour/label per tier and correct width calculation

### Implementation for User Story 3

#### Backend endpoints

- [X] T030 [US3] Add `DeviceCreditDetail` Pydantic response model and `GET /api/v1/devices/{device_id}/credits` endpoint to `src/api/routers/devices.py` — returns `credit_balance`, `reward_tier`, `streak_days`, `cumulative_credits_earned`, `cumulative_credits_spent`, `next_tier`, `credits_to_next_tier` (computed from active config), `tier_multiplier`, `tier_discount`
- [X] T031 [US3] Add `TransactionHistoryResponse` Pydantic model and `GET /api/v1/devices/{device_id}/credits/transactions` endpoint to `src/api/routers/devices.py` — query params: `limit` (default 50, max 200), `offset` (default 0), `action_type` (optional); returns total count + paginated `CreditTransaction` list in reverse-chronological order
- [X] T032 [US3] Extend `POST /api/v1/devices/{device_id}/credits` in `src/api/routers/devices.py` — add optional `reason: str` field to `TopUpRequest`; write `CreditTransaction` row via `ledger.update_device_balance` with `action_type=top_up` and the provided reason (default: "manual top-up"); update `cumulative_credits_earned`

#### React frontend

- [X] T033 [US3] Implement `frontend/src/api/creditApi.ts` — typed fetch wrappers for: `getCreditConfig()`, `updateCreditConfig(data)`, `getDeviceCredits(deviceId)`, `getDeviceTransactions(deviceId, params)`, `topUpCredits(deviceId, amount, reason)`; read API key from `sessionStorage`; proxy to `/api`
- [X] T034 [P] [US3] Implement `frontend/src/components/TierBadge.tsx` — coloured pill badge (Bronze=amber, Silver=gray, Gold=yellow, Platinum=cyan) displaying tier name
- [X] T035 [P] [US3] Implement `frontend/src/components/TierProgressBar.tsx` — progress bar showing `cumulative_credits_earned / next_tier_threshold` with label "X credits to {next_tier}" (renders "MAX TIER" when Platinum)
- [X] T036 [P] [US3] Implement `frontend/src/components/TransactionTable.tsx` — paginated table with columns: timestamp, type badge, amount (green +N / red -N), reason, balance after; uses TanStack Query for data fetching
- [X] T037 [US3] Implement `frontend/src/pages/DeviceCreditsPage.tsx` — device ID search input, renders balance card (balance + tier badge + streak count), `TierProgressBar`, and `TransactionTable`; shows 404 message for unknown device
- [X] T038 [US3] Implement `frontend/src/App.tsx` — client-side routing (React Router or hash router) between `DeviceCreditsPage` and `AdminConfigPage`; API key input form stored in `sessionStorage`; global error boundary
- [X] T039 [US3] Wire `frontend/src/main.tsx` entry point; add `QueryClientProvider`; run `npm run build` and verify static output in `frontend/dist/`

**Checkpoint**: `make up` starts all services; open `http://localhost:3200`; enter a seeded device ID; see balance, tier badge, streak, progress bar, and transaction history rendered.

---

## Phase 6: User Story 4 — Tiered Reward Progression (Priority: P2)

**Goal**: Devices automatically advance through Bronze→Silver→Gold→Platinum tiers as `cumulative_credits_earned` crosses configurable thresholds. Higher tiers earn more credits (multiplier) and pay less (discount). Admin can manage thresholds via UI.

**Independent Test**: Set device `cumulative_credits_earned` to 499 (just below Silver), ingest a workout event that earns enough to cross 500 → device tier changes to Silver; subsequent earning shows 1.25× multiplier applied.

### Tests for User Story 4 (TDD — write first, confirm they fail, then implement)

- [X] T040 [P] [US4] Write unit tests for `TierEngine` tier transitions in `tests/unit/test_tier_progression.py`: test bronze→silver at threshold, silver→gold, gold→platinum; test multiplier lookup per tier; test tier never decreases; test thresholds loaded from custom config
- [X] T041 [P] [US4] Write integration test for automatic tier upgrade in `tests/integration/test_tier_progression.py`: seed device at cumulative_credits_earned=499, ingest workout event with earning rule ≥ 1 → assert tier changed to silver in DB and response shows `reward_tier: "silver"`

### Implementation for User Story 4

- [X] T042 [US4] Wire tier recompute into `EarningService.award_for_event` in `src/credits/earning_service.py` — after updating `cumulative_credits_earned`, call `tier_engine.compute_tier_from_config(device.cumulative_credits_earned, config)`, compare with `device.reward_tier`, update if promoted, emit `CREDIT_TIER_TOTAL` Prometheus metric update on tier change, log `tier_upgraded` event
- [X] T043 [US4] Implement `frontend/src/pages/AdminConfigPage.tsx` — form with sections: Default Balance, Activity Earning Rules (dynamic key-value rows per scenario), Service Costs (per service), Streak Bonuses, Tier Thresholds (4 inputs), Tier Multipliers (4 inputs), Tier Discounts (4 inputs); inline validation feedback; submit calls `updateCreditConfig`; success toast; loads current config on mount via `getCreditConfig`
- [X] T044 [US4] Link `AdminConfigPage` into navigation in `frontend/src/App.tsx` (tab or sidebar link "Admin → Credit Config"); ensure config changes in AdminConfigPage are reflected in DeviceCreditsPage tier progress after refresh

**Checkpoint**: Update tier thresholds in AdminConfigPage → ingest events to push a device across a new threshold → verify tier badge updates on DeviceCreditsPage; unit tests for TierEngine pass.

---

## Phase 7: User Story 5 — Grafana Credits Dashboard (Priority: P3)

**Goal**: Pre-configured Grafana dashboard showing 6 credit panels auto-provisions on `docker compose up`.

**Independent Test**: Run `make up`; open Grafana at `http://localhost:3100`; navigate to Dashboards → Credits & Rewards; all 6 panels render with data.

### Implementation for User Story 5

- [X] T045 [P] [US5] Create `infra/grafana/provisioning/dashboards/credits.json` — Grafana dashboard JSON with 6 panels:
  1. **Credits Balance by Device** (table, sorted desc) — query: `device_credit_balance`
  2. **Credits Earned vs Spent over Time** (time series, 2 series) — queries: `rate(device_credits_earned_total[5m])`, `rate(device_credits_spent_total[5m])`
  3. **Tier Distribution** (pie chart) — query: `credit_tier_total` grouped by `tier` label
  4. **Top Credit Spenders (last 24h)** (table, top 10) — query: `increase(device_credits_spent_total[24h])` topk 10
  5. **Streak Leaderboard** (table, top 10) — query: `device_streak_days` topk 10
  6. **Activity Type Breakdown** (bar, by `action_type`) — query: `increase(device_credits_earned_total[24h])` grouped by `action_type` (requires metric label)
- [X] T046 [P] [US5] Add `action_type` label to `DEVICE_CREDITS_EARNED` Counter in `src/observability/metrics.py` so the activity breakdown panel can distinguish `activity_reward` from `streak_bonus` from `top_up`
- [X] T047 [US5] Verify Grafana datasource UID matches `infra/grafana/provisioning/datasources/prometheus.yml`; update dashboard JSON `datasource` references to use the correct UID; run `make up` and confirm all panels load without errors

**Checkpoint**: All 6 Grafana panels show data after seeding with `make seed` and ingesting test events.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, integration fixes, and documentation.

- [X] T048 [P] Run full backend test suite `make test` — fix any regressions introduced by schema changes (e.g. `test_recommendation_deducts_credit` after cost becomes config-driven); ensure 51+ tests pass
- [X] T049 [P] Run `make test-frontend` — verify all Vitest component tests pass; fix any TS type errors
- [X] T050 Update `scripts/seed_devices.py` if needed — ensure seeded devices are compatible with new Device model columns (`streak_days=0`, `last_activity_date=None`, `cumulative_credits_earned=0`); confirm `make seed` succeeds
- [X] T051 Validate full quickstart.md walkthrough: execute all 9 steps sequentially, verify every `curl` command returns expected output, Grafana dashboard loads, React UI shows data; fix any discrepancies found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup → **BLOCKS all user stories**
- **US1 (Phase 3)**: Requires Phase 2 complete
- **US2 (Phase 4)**: Requires Phase 2 + US1 complete (needs ConfigService for earning rules, service costs)
- **US3 (Phase 5)**: Requires Phase 2 + US2 complete (needs EarningService writing transactions to display)
- **US4 (Phase 6)**: Requires Phase 2 + US2 complete (tier recompute is part of EarningService)
- **US5 (Phase 7)**: Requires Phase 2 + US2 complete (needs Prometheus metrics populated)
- **Polish (Phase 8)**: Requires all desired user stories complete

### User Story Dependencies

- **US1 (P1 — Config)**: Unblocks US2 (earning rules come from config)
- **US2 (P1 — Earning)**: Unblocks US3 (transactions to display), US4 (tier recompute hook), US5 (metrics to chart)
- **US3 (P2 — React UI)**: Independent of US4/US5 once US2 is done
- **US4 (P2 — Tier Progression)**: Independent of US3/US5 once US2 is done
- **US5 (P3 — Grafana)**: Independent of US3/US4 once US2 is done

### Within Each User Story

- Tests FIRST → confirm they fail → implement → confirm they pass
- Models/services before endpoints
- Backend endpoints before frontend consumers

### Parallel Opportunities

- T002, T003, T004 (Setup) — can run in parallel
- T007, T008 (Foundational model extensions) — can run in parallel (different files)
- T011, T012 (US1 tests) — can run in parallel
- T020, T021 (US2 tests) — can run in parallel
- T028, T029 (US3 tests) — can run in parallel
- T034, T035, T036 (US3 React components) — can run in parallel
- T040, T041 (US4 tests) — can run in parallel
- T045, T046 (US5 Grafana + metrics) — can run in parallel
- T048, T049 (Polish test runs) — can run in parallel

---

## Parallel Example: User Story 2 (Earning)

```bash
# Parallel: write both test files at the same time
Task T020: "Write unit tests for EarningService in tests/unit/test_earning_service.py"
Task T021: "Write integration tests for activity earning in tests/integration/test_activity_earning.py"

# Then sequential implementation:
Task T022: TierEngine → Task T023: Ledger → Task T024: EarningService → Task T025: Ingest hook
```

---

## Implementation Strategy

### MVP First (US1 + US2 only — backend, no frontend)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (DB migration + ORM extensions)
3. Complete Phase 3: US1 (credit config API)
4. Complete Phase 4: US2 (activity earning + transactions)
5. **STOP and VALIDATE**: `make test` passes; `make seed` + ingest events → credits awarded; transaction log populated
6. Demo-able via `curl` without frontend

### Incremental Delivery

1. Setup + Foundational → Foundation ready (make test still passes)
2. US1 (Config API) → admin can control credit rules
3. US2 (Earning) → devices earn credits from activities → **shippable PoC backend**
4. US3 (React UI) → operators can inspect any device's credit state visually
5. US4 (Tier Progression) → full reward loop with automatic upgrades and multipliers
6. US5 (Grafana) → fleet-wide credit economics visible to platform team

---

## Notes

- `[P]` tasks touch different files and have no shared dependencies within a phase
- `[Story]` label maps each task to its user story for traceability and independent deployment
- Constitution Principle II (TDD) requires tests to be written and failing BEFORE implementation
- All DB writes go through `ledger.update_device_balance` — never update `credit_balance` directly in routers
- `CreditConfig` is the single source of truth for all numeric rules; `Settings.initial_credit_balance` remains as a bootstrap fallback only
- Tier computation uses `cumulative_credits_earned` (NOT `cumulative_credits_spent`) per spec FR-015
