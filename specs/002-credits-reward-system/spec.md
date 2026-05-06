# Feature Specification: Device Credits Management and Tiered Reward System

**Feature Branch**: `002-credits-reward-system`
**Created**: 2026-05-04
**Status**: Draft
**Input**: User description: "Create a feature with Device Credits Management and Tiered Reward System"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Credit Configuration Management (Priority: P1)

A platform administrator needs to define the economic rules that govern the credit system: how many credits a new device starts with, how much each type of health recommendation costs, and how much each activity scenario earns. These rules must be configurable without a deployment.

**Why this priority**: Without credit rules there is nothing to earn or spend — every other story depends on this foundation being in place.

**Independent Test**: Can be fully tested by an admin opening the configuration panel, setting default credit values and activity earning rates, saving the configuration, and verifying the saved values persist and are returned when the config is fetched again.

**Acceptance Scenarios**:

1. **Given** the admin opens the credit configuration panel, **When** they set the default initial balance for new devices to 200 credits, **Then** the next registered device receives exactly 200 credits on registration.
2. **Given** the admin is on the service pricing screen, **When** they set recommendation service A to cost 3 credits and service B to cost 5 credits, **Then** subsequent calls to each service deduct the configured amount from the device balance.
3. **Given** an activity earning rule exists for "workout" at 10 credits, **When** the admin updates it to 15 credits and saves, **Then** new workout telemetry events earn 15 credits immediately without restarting the system.
4. **Given** invalid values (negative credits, zero cost for a service), **When** the admin submits the form, **Then** validation errors are shown inline and no values are saved.

---

### User Story 2 - Earning Credits Through Health Activities (Priority: P1)

Device users (i.e., the wearable devices sending health data) earn credits by demonstrating healthy behaviours. Higher-intensity activities should earn more credits than passive monitoring. Consistent daily data submission should be rewarded with a streak bonus. The credit balance and tier are updated automatically as events arrive — no manual action by the user.

**Why this priority**: Earning mechanics drive the incentive loop. Without earning, the credit balance only decreases and users have no motivation to engage.

**Independent Test**: Can be fully tested by submitting telemetry events with different scenario types and verifying the correct credit amount is added to the device balance each time, including streak multipliers after consecutive days.

**Acceptance Scenarios**:

1. **Given** a device sends a telemetry event with scenario "workout", **When** the event is validated and stored, **Then** the device earns the configured workout credit amount (default: 10 credits).
2. **Given** a device sends a telemetry event with scenario "sleep", **When** the event is processed, **Then** the device earns the configured sleep credit amount (default: 3 credits — less than workout, rewarding active effort more).
3. **Given** a device has sent data every day for 7 consecutive days, **When** the 7th event arrives, **Then** a streak bonus of 5 credits is awarded in addition to the activity credits.
4. **Given** a device is on a 14-day streak and misses a day, **When** the next event arrives the following day, **Then** the streak counter resets to 1 and no streak bonus is awarded.
5. **Given** a device sends two telemetry events of the same scenario within the same hour, **When** both are processed, **Then** only the first earns activity credits (duplicate-window deduplication prevents abuse).

---

### User Story 3 - Credit Balance and Tier Visibility (Priority: P2)

A device owner or platform operator needs a React web interface to inspect any device's current credit balance, reward tier, progress toward the next tier, and a transaction history showing every credit earned and spent with the reason attached.

**Why this priority**: Transparency drives engagement. Users and operators need to see the credit state to trust the system and act on it. This is a read-heavy UI story with no blocking dependencies on story 2 being fully complete.

**Independent Test**: Can be fully tested by navigating to a device's credit page and verifying balance, tier badge, tier progress bar, and last 50 transactions are all visible and correct.

**Acceptance Scenarios**:

1. **Given** a device has 150 credits and "silver" tier, **When** the user opens the device credit page, **Then** they see "150 credits", a Silver tier badge, and a progress bar showing distance to Gold tier.
2. **Given** a device has 10 credit transactions, **When** the transaction history panel is viewed, **Then** all 10 entries are listed in reverse chronological order with type (earned/spent), amount, reason (e.g., "workout activity", "service1 recommendation"), and timestamp.
3. **Given** a platform admin manually tops up a device with 50 credits, **When** the page is refreshed, **Then** the new balance is reflected and the top-up appears as a transaction entry with reason "manual top-up".
4. **Given** a device with zero balance attempts to request a recommendation, **When** the request arrives, **Then** a 402 response is returned and a transaction entry shows "insufficient credits — request rejected".

---

### User Story 4 - Tiered Reward Progression (Priority: P2)

Devices that accumulate high cumulative credit activity are promoted through tiers (Bronze → Silver → Gold → Platinum). Higher tiers earn multiplied credits per activity, reducing the effective cost of recommendations and rewarding long-term engagement. Tier upgrades happen automatically when thresholds are crossed.

**Why this priority**: Tiers are the long-term retention mechanic. They add aspiration beyond just maintaining a balance, mirroring proven fitness app engagement patterns (Fitbit, Garmin, Apple Fitness+).

**Independent Test**: Can be fully tested by setting a device's cumulative credits to just below a tier threshold, then submitting one activity event that crosses the threshold, and verifying the tier badge updates and the earning multiplier changes.

**Acceptance Scenarios**:

1. **Given** cumulative credits thresholds are Bronze < 500, Silver ≥ 500, Gold ≥ 1500, Platinum ≥ 5000, **When** a device's cumulative earned credits reach 500, **Then** the device tier changes to Silver automatically.
2. **Given** a Silver-tier device earns 10 credits for a workout, **When** the Silver multiplier is 1.25×, **Then** the actual credit award is 12 or 13 credits (rounded up), and the difference is reflected in the transaction log.
3. **Given** a Platinum-tier device, **When** it requests a recommendation, **Then** the credit cost is discounted by the Platinum discount rate (default: 20% reduction).
4. **Given** a device's tier has just changed to Gold, **When** the device credit page is viewed, **Then** a visual indicator highlights the tier-up event with the unlock date.

---

### User Story 5 - Grafana Credits Dashboard (Priority: P3)

Platform operators and data analysts need a pre-configured Grafana dashboard showing credit economics across all devices: who is earning, who is spending, tier distribution, and activity breakdown. This enables monitoring of system health and early detection of anomalies (e.g., devices draining credits unexpectedly).

**Why this priority**: Monitoring closes the feedback loop for operators. It is P3 because it does not block any device-facing functionality and can be added after the core mechanics work.

**Independent Test**: Can be fully tested by opening the Grafana dashboard and verifying all six panels render with data, correct labels, and sensible axes.

**Acceptance Scenarios**:

1. **Given** the Grafana dashboard is opened, **When** data exists, **Then** a "Credits Balance by Device" panel shows current balance ranked highest to lowest.
2. **Given** the time range is set to "last 7 days", **When** the "Credits Earned vs Spent" panel is viewed, **Then** it shows a stacked bar or area chart with separate series for earned and spent per day.
3. **Given** devices span multiple tiers, **When** the "Tier Distribution" panel is viewed, **Then** it shows a pie or donut chart with Bronze / Silver / Gold / Platinum slices.
4. **Given** a device has unusual credit drain (>50 credits spent in 1 hour), **When** the "Top Credit Spenders (Last 24h)" panel is viewed, **Then** that device appears prominently at the top of the list.

---

### Edge Cases

- What happens when a device's credit balance would go negative after a transaction? The transaction must be rejected with a clear error; the balance never goes below zero.
- What happens if two telemetry events arrive simultaneously for the same device? Credit award must be idempotent per event ID — duplicate events are deduplicated before credits are issued.
- What happens when an admin lowers the credit cost for a service type? Historical transactions are unaffected; only future requests use the new cost.
- What happens if a new device registers after default credits are changed? The new default applies; previously registered devices are unaffected.
- What happens when a tier threshold is reconfigured to be lower than a device's current cumulative? Devices keep their existing tier; threshold changes do not retroactively downgrade tiers.

## Requirements *(mandatory)*

### Functional Requirements

**Credit Configuration**

- **FR-001**: System MUST allow administrators to set a default initial credit balance applied to every newly registered device (default: 100 credits).
- **FR-002**: System MUST allow administrators to configure a credit cost per recommendation service type (minimum: 1 credit per service call, no upper limit).
- **FR-003**: System MUST allow administrators to configure credit earning amounts per telemetry activity scenario (workout, sport, sleep, rest, and a generic fallback for unmapped scenarios).
- **FR-004**: Credit configuration changes MUST take effect for all subsequent events within 10 seconds of saving; no system restart required.
- **FR-005**: System MUST reject credit configuration values that would make any service free (0 cost) or that set earning amounts to negative numbers.

**Credit Earning**

- **FR-006**: System MUST automatically award credits to a device when a valid telemetry event is received, using the earning rule that matches the event's activity scenario.
- **FR-007**: Workout and sport scenarios MUST earn more credits than rest and sleep scenarios by default, encoding the principle that active effort is rewarded more than passive monitoring.
- **FR-008**: System MUST track a consecutive-day activity streak per device and award a configurable streak bonus when the streak reaches 7 and 30 consecutive days.
- **FR-009**: System MUST deduplicate credit awards per telemetry event ID so that re-ingested events do not award credits twice.
- **FR-010**: System MUST record every credit transaction with: device ID, transaction type (earned/spent/bonus/top-up/adjustment), amount, reason description, related entity ID (event ID or recommendation request ID), and timestamp.

**Credit Spending**

- **FR-011**: System MUST deduct the configured credit cost from a device's balance when a recommendation is successfully fulfilled.
- **FR-012**: System MUST reject recommendation requests from devices with insufficient balance, returning a clear error without deducting credits.
- **FR-013**: Tier-based discounts MUST reduce the effective spend cost for Gold and Platinum tier devices.

**Reward Tiers**

- **FR-014**: System MUST support four named tiers: Bronze (default), Silver, Gold, Platinum, each with a configurable cumulative credit threshold.
- **FR-015**: System MUST automatically promote a device to the next tier when its cumulative earned credits cross the tier threshold; tier promotions are permanent and never reversed.
- **FR-016**: Each tier MUST carry a configurable earning multiplier applied to all activity credit awards (Bronze: 1.0×, Silver: 1.25×, Gold: 1.5×, Platinum: 2.0× by default).

**React Frontend**

- **FR-017**: System MUST provide a web interface where any device's credit balance, current tier, tier progress, and full transaction history can be viewed by entering the device ID.
- **FR-018**: System MUST provide an admin configuration screen for managing credit rules (default balance, service costs, activity earning rates, streak bonuses, tier thresholds and multipliers).
- **FR-019**: The frontend MUST allow an authorised admin to manually top up or adjust a device's credit balance with a mandatory reason field.
- **FR-020**: The frontend MUST display tier progress as a visual indicator showing credits accumulated toward the next tier boundary.

**Grafana Dashboard**

- **FR-021**: System MUST expose Prometheus metrics for: current credit balance per device, total credits earned per device, total credits spent per device, active streak length per device, and tier distribution count.
- **FR-022**: A pre-configured Grafana dashboard MUST include panels for: credits balance ranking, earned vs spent over time, tier distribution, top spenders (last 24 h), streak leaderboard, and activity type credit breakdown.

### Key Entities

- **CreditConfig**: Global configuration record holding default initial balance, per-service costs, per-scenario earning amounts, streak bonus amounts, and tier thresholds/multipliers. Only one active config exists at a time; changes are versioned for audit.
- **DeviceCredit**: Per-device record holding current balance, cumulative credits earned, cumulative credits spent, current tier, active streak length, and last activity date. Updated atomically on each qualifying event.
- **CreditTransaction**: Immutable audit record for every credit change — device ID, type, delta amount, running balance after, reason text, source entity ID, and UTC timestamp.
- **ActivityCreditRule**: Named mapping from telemetry scenario label to base credit award amount (e.g., "workout" → 10, "sleep" → 3). Part of CreditConfig.
- **RewardTier**: Named tier with cumulative threshold, earning multiplier, and recommendation discount rate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can view and update any credit configuration value within 60 seconds of opening the configuration panel.
- **SC-002**: Credit balances reflect earned or spent credits within 5 seconds of the triggering event being ingested.
- **SC-003**: The Grafana dashboard loads with all panels populated within 10 seconds for up to 10,000 devices tracked.
- **SC-004**: A device owner can identify their current tier, current balance, and credits needed to reach the next tier in a single screen view without scrolling.
- **SC-005**: 100% of credit transactions are recorded in the audit log with correct device, amount, and reason — verified by comparing transaction totals against balance history.
- **SC-006**: Devices on streak streaks show measurably higher average daily telemetry submission rates than non-streak devices (target: ≥ 20% higher submission rate for streak devices after 30 days in production).
- **SC-007**: The React frontend is usable on desktop and tablet viewports (≥ 768px wide) without horizontal scrolling or hidden content.

## Assumptions

- The existing backend already tracks `credit_balance`, `cumulative_credits_spent`, and `reward_tier` on the Device model; this feature extends that data rather than replacing it.
- The existing recommendation flow already deducts one credit per call; this feature makes the per-service cost configurable and adds earning mechanics.
- Authentication for the admin frontend will use the existing `X-API-Key` mechanism already in place; no new auth system is needed for the PoC.
- Streak tracking is based on calendar days in UTC; a device that sends at least one valid telemetry event per calendar day maintains its streak.
- Credit configuration is global (same rules for all devices); per-device overrides are out of scope for this PoC.
- The React frontend will be served as a static build via the existing platform or a lightweight static host; no separate backend is needed beyond the existing REST API.
- Tier downgrades are out of scope; tiers only move upward, simplifying the rules and avoiding penalising users for inactive periods.
- Grafana metrics are pulled from Prometheus; the existing Prometheus setup in docker-compose is extended with new metric exports, not replaced.
- Maximum supported devices for the PoC dashboard is 10,000; larger fleets are out of scope.
