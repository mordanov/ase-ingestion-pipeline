# Research: Device Credits Management and Tiered Reward System

**Feature**: 002-credits-reward-system
**Date**: 2026-05-04

---

## Decision 1: Frontend Technology

**Decision**: React 18 + TypeScript + Vite for the admin/credits UI

**Rationale**: The spec explicitly requires a React.js frontend. Vite is the current standard build tool for React (faster than CRA, native ESM, excellent HMR). TypeScript adds type safety that matches the Python-typed backend. The existing backend already has permissive CORS middleware (`allow_origins=["*"]`) making local dev trivial.

**Alternatives considered**:
- Plain HTML + Fetch API — rejected: too low-level for forms, tables, tier progress components
- Next.js — rejected: SSR overhead unjustified for an internal admin PoC
- Vue/Svelte — rejected: spec says React.js explicitly

**Constitution note**: Constitution says "Python 3.11+ (primary); other runtimes permitted for edge/device SDKs." The React frontend is a UI layer, not a backend SDK — it is permitted by the "other runtimes permitted" clause. Backend remains 100% Python. Deviation is documented here per the amendment procedure.

---

## Decision 2: Frontend Serving in docker-compose

**Decision**: Multi-stage Docker build: `node:20-alpine` build stage → `nginx:alpine` serve stage. Added as `frontend` service in `docker-compose.yml` on port 3200.

**Rationale**: Static files served by nginx have near-zero runtime overhead. Vite dev proxy (`/api` → `http://app:8000`) is used for local development without rebuilding. The Makefile will add a `make frontend-dev` target for hot-reload development.

**Alternatives considered**:
- Serve React static files from FastAPI `StaticFiles` — rejected: couples frontend and backend deploy cycles
- Vite dev server only — rejected: no production serving path

---

## Decision 3: CreditConfig Storage

**Decision**: Single active row in a `credit_config` PostgreSQL table, version-stamped for audit. Loaded from DB per-request (no cache) for PoC; a short TTL cache can be added in production.

**Rationale**: FR-004 requires changes to take effect within 10 seconds without a restart. Environment variables and config files require restarts. A DB row is updatable via the admin API immediately and survives container restarts.

**Alternatives considered**:
- Environment variables (`initial_credit_balance` already exists in Settings) — rejected: requires restart, not hot-updatable
- Redis key-value — rejected: extra dependency not needed since PostgreSQL is already present

---

## Decision 4: Activity Credit Earning Hook

**Decision**: Call `EarningService.award_for_event(event, session)` from the existing ingest router **after** the `TelemetryEvent` is persisted but **before** the final commit, using the same database transaction.

**Rationale**: Atomicity — if the commit rolls back (e.g., IntegrityError), no credits are awarded. No extra queue or worker needed. Keeps earning in the same request context.

**Earning rule lookup**: `EarningService` loads `CreditConfig` from the DB (or a short in-memory cache) and looks up the base earn amount by `event.scenario`. Applies the device's tier multiplier. Inserts a `CreditTransaction` row and increments `Device.credit_balance` and `Device.cumulative_credits_earned` in the same transaction.

**Alternatives considered**:
- Separate async worker polling for new events — rejected: latency > 5s, extra infrastructure
- Kafka consumer post-processing — rejected: overkill for PoC, latency overhead

---

## Decision 5: Streak Tracking

**Decision**: Two new columns on `Device`: `streak_days: int` (default 0) and `last_activity_date: date` (nullable). Updated by `EarningService` on each qualifying event.

**Logic**: On each event, compare `event.event_timestamp.date()` with `device.last_activity_date`. If same day: no streak update (idempotent). If yesterday: `streak_days += 1`, `last_activity_date = today`. If gap > 1 day: `streak_days = 1`, `last_activity_date = today`. Streak bonuses awarded at 7 and 30 consecutive days (one bonus per threshold crossing, tracked by a new `CreditActionType.streak_bonus`).

**Alternatives considered**:
- Separate `device_streaks` table — rejected: extra join on every ingest event; streak is a simple per-device scalar
- Compute streak from transaction history on-read — rejected: O(n) scan, violates real-time performance principle

---

## Decision 6: Tier Progression Basis

**Decision**: Tier is computed from `cumulative_credits_earned` (total ever earned), **not** `cumulative_credits_spent` (what is currently tracked on `Device`). A new `cumulative_credits_earned: int` column is added to `Device`.

**Rationale**: The spec (FR-015) says "cumulative earned credits cross the tier threshold." Earned credits measure total engagement. Spent credits measure service usage — a user could game the system by spending borrowed credits without earning them.

**Impact on existing code**: The current `TierEngine.compute_tier(cumulative_spent)` call in `recommendations.py` must be updated to pass `cumulative_earned` instead.

---

## Decision 7: CreditTransaction Schema Extension

**Decision**: Extend `CreditTransaction` with `reason: str` (human-readable) and `metadata: JSONB` (source entity ID, event_id, etc.). Extend `CreditActionType` enum with: `activity_reward`, `streak_bonus`, `adjustment` (admin manual), `tier_discount`.

**Rationale**: The spec requires full audit log (FR-010). The current table has no reason field. `JSONB` metadata preserves flexibility without schema changes for new metadata shapes.

**Migration**: A new Alembic migration `002_credits_extended.py` adds the columns and new enum values.

---

## Decision 8: Prometheus Metrics for Credits

**Decision**: Add Gauge metrics updated on each write operation (not scraped from DB on demand):
- `device_credit_balance{device_id}` — current balance after each transaction
- `device_credits_earned_total{device_id}` — cumulative earned
- `device_credits_spent_total{device_id}` — cumulative spent
- `device_streak_days{device_id}` — current streak
- `credit_tier_total{tier}` — count of devices per tier (updated on tier change)

**Rationale**: Prometheus push-on-write pattern avoids a full DB scan on every Prometheus scrape. For PoC scale (≤ 10,000 devices) in-process Gauge labels are acceptable. In production, a separate exporter querying the DB would be more appropriate.

---

## Decision 9: Grafana Dashboard Provisioning

**Decision**: New JSON dashboard provisioned at `infra/grafana/provisioning/dashboards/credits.json` with 6 panels: (1) Credits Balance by Device (table), (2) Earned vs Spent over time (time series), (3) Tier Distribution (pie), (4) Top Credit Spenders last 24h (table), (5) Streak Leaderboard (table), (6) Activity Type Breakdown (bar).

**Rationale**: Provisioning via JSON means the dashboard appears on first `docker compose up` with no manual Grafana clicks, satisfying the "15-minute quickstart" requirement.
