# Data Model: Device Credits Management and Tiered Reward System

**Feature**: 002-credits-reward-system
**Date**: 2026-05-04

---

## Entities

### Device (extended)

Extends the existing `devices` table with streak and cumulative earning fields.

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `streak_days` | int | No | Consecutive calendar days with at least one valid telemetry event. Default 0. |
| `last_activity_date` | date | Yes | UTC calendar date of the most recent qualifying event. NULL until first event. |
| `cumulative_credits_earned` | int | No | Total credits ever earned (activity + bonuses + top-ups). Used for tier computation. Default 0. |

**Existing fields retained**: `credit_balance`, `cumulative_credits_spent`, `reward_tier`.

**Tier update rule**: After `cumulative_credits_earned` changes, recompute tier using thresholds from `CreditConfig`. Tier never decreases.

---

### CreditConfig

Single active configuration row governing the entire credit economy. Only one row with `is_active = TRUE` exists at a time; prior rows are retained for audit.

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `id` | UUID | No | Primary key |
| `version` | int | No | Monotonically increasing. Current active config has the highest version. |
| `is_active` | bool | No | Only one row is `TRUE`. |
| `default_initial_balance` | int | No | Credits granted to a new device on registration. Default 100. |
| `activity_earning_rules` | JSONB | No | Map of scenario name → base credit award. E.g. `{"workout": 10, "sport": 8, "rest": 2, "sleep": 3, "default": 2}`. |
| `service_costs` | JSONB | No | Map of service identifier → credit cost. E.g. `{"service1": 3, "service2": 5, "default": 1}`. |
| `streak_bonus_7d` | int | No | Bonus credits awarded when 7-day streak is first achieved. Default 5. |
| `streak_bonus_30d` | int | No | Bonus credits awarded when 30-day streak is first achieved. Default 20. |
| `tier_thresholds` | JSONB | No | Map of tier name → cumulative earned threshold. E.g. `{"bronze": 0, "silver": 500, "gold": 1500, "platinum": 5000}`. |
| `tier_multipliers` | JSONB | No | Map of tier name → earning multiplier. E.g. `{"bronze": 1.0, "silver": 1.25, "gold": 1.5, "platinum": 2.0}`. |
| `tier_discounts` | JSONB | No | Map of tier name → recommendation cost reduction fraction. E.g. `{"bronze": 0.0, "silver": 0.0, "gold": 0.1, "platinum": 0.2}`. |
| `created_at` | timestamptz | No | When this version was created. |
| `created_by` | varchar(128) | Yes | API key hash or admin identifier. |

**Validation rules**:
- All earning amounts ≥ 0 (earning 0 for an unlisted scenario is allowed)
- All service costs ≥ 1 (services must cost at least 1 credit)
- Tier thresholds must be strictly ascending: bronze < silver < gold < platinum
- Tier multipliers must be ≥ 1.0
- Tier discounts must be in range [0.0, 1.0)

---

### CreditTransaction (extended)

Immutable audit log of every credit change. Extends existing table with `reason` and `metadata` fields and new enum values.

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `id` | UUID | No | Primary key |
| `device_id` | varchar(128) | No | FK → devices.device_id |
| `amount` | int | No | Signed delta. Positive = earned, negative = spent/deducted. |
| `action_type` | enum | No | See action types below. |
| `resulting_balance` | int | No | Balance after this transaction was applied. |
| `reason` | varchar(256) | No | Human-readable description. E.g. "workout activity reward", "service1 recommendation", "7-day streak bonus". |
| `metadata` | JSONB | Yes | Structured context. E.g. `{"event_id": "...", "scenario": "workout", "tier": "silver", "multiplier": 1.25}`. |
| `created_at` | timestamptz | No | UTC timestamp of the transaction. |

**CreditActionType enum values** (extended from existing):

| Value | Direction | Description |
|-------|-----------|-------------|
| `recommendation` | negative | Credit spent on a recommendation request |
| `registration_bonus` | positive | Initial credits on device registration |
| `top_up` | positive | Manual admin top-up |
| `activity_reward` | positive | Credits earned from a telemetry activity event |
| `streak_bonus` | positive | Bonus for reaching 7-day or 30-day streak milestone |
| `tier_discount` | negative adjustment | Discount applied to a recommendation (stored as separate line to show effective cost) |
| `adjustment` | either | Manual admin balance adjustment (with mandatory reason) |

---

## State Transitions

### Device Credit Balance

```
[Registration] → balance = CreditConfig.default_initial_balance
                 action_type = registration_bonus
                 cumulative_credits_earned += default_initial_balance

[Telemetry Event Arrives] → check if earning rule exists for scenario
                            base_amount = config.activity_earning_rules[scenario] or default
                            multiplier = config.tier_multipliers[device.reward_tier]
                            award = ceil(base_amount * multiplier)
                            balance += award
                            cumulative_credits_earned += award
                            action_type = activity_reward
                            → check streak → maybe streak_bonus

[Streak Milestone (7d / 30d)] → bonus = config.streak_bonus_7d / streak_bonus_30d
                                 balance += bonus
                                 cumulative_credits_earned += bonus
                                 action_type = streak_bonus

[Recommendation Request] → check balance >= effective_cost
                           if insufficient → reject (402), no transaction
                           discount = config.tier_discounts[device.reward_tier]
                           effective_cost = ceil(base_cost * (1 - discount))
                           balance -= effective_cost
                           cumulative_credits_spent += effective_cost
                           action_type = recommendation

[Admin Top-Up / Adjustment] → balance += amount (positive or negative)
                               if top_up: cumulative_credits_earned += amount
                               action_type = top_up | adjustment
```

### Device Reward Tier

```
[On cumulative_credits_earned update]:
  for tier in [platinum, gold, silver, bronze]:  # descending order
    if cumulative_credits_earned >= config.tier_thresholds[tier]:
      new_tier = tier
      break
  if new_tier > device.reward_tier:  # only upgrade
    device.reward_tier = new_tier
```

---

## Relationships

```
CreditConfig (1) ─────────────── (used by) EarningService, TierEngine
Device       (1) ─────────────── (many) CreditTransaction
             .reward_tier, .credit_balance, .streak_days, .cumulative_credits_earned
```

---

## PII Annotation

- `Device.user_id`, `Device.height_cm`, `Device.weight_kg` remain PII — never returned in credit API responses
- `CreditTransaction.device_id` is a device business key, not directly a user identifier — acceptable to include in audit log
- `CreditConfig.created_by` should store an anonymised admin identifier (e.g., API key prefix), not a full user name
