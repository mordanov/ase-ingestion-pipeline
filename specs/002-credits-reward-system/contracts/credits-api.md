# API Contract: Credits & Reward System

**Feature**: 002-credits-reward-system
**Base URL**: `/api/v1`
**Auth**: All endpoints require `X-API-Key` header (matching `API_KEY` env var).

---

## GET /api/v1/credit-config

Returns the currently active credit configuration.

**Response 200**:
```json
{
  "version": 3,
  "default_initial_balance": 100,
  "activity_earning_rules": {
    "workout": 10,
    "sport": 8,
    "sleep": 3,
    "rest": 2,
    "default": 2
  },
  "service_costs": {
    "service1": 3,
    "service2": 5,
    "default": 1
  },
  "streak_bonus_7d": 5,
  "streak_bonus_30d": 20,
  "tier_thresholds": {
    "bronze": 0,
    "silver": 500,
    "gold": 1500,
    "platinum": 5000
  },
  "tier_multipliers": {
    "bronze": 1.0,
    "silver": 1.25,
    "gold": 1.5,
    "platinum": 2.0
  },
  "tier_discounts": {
    "bronze": 0.0,
    "silver": 0.0,
    "gold": 0.1,
    "platinum": 0.2
  },
  "created_at": "2026-05-04T10:00:00Z"
}
```

---

## PUT /api/v1/credit-config

Replaces the active credit configuration. Creates a new versioned row; prior config is retained for audit.

**Request body**: Same shape as GET response (without `version`, `created_at`).

**Validation errors (422)**:
- Any `service_costs` value < 1
- Any `activity_earning_rules` value < 0
- `tier_thresholds` not strictly ascending
- Any `tier_multipliers` value < 1.0
- Any `tier_discounts` value outside [0.0, 1.0)

**Response 200**: Updated config (same shape as GET response).

---

## GET /api/v1/devices/{device_id}/credits

Returns credit detail for a single device including tier progress.

**Response 200**:
```json
{
  "device_id": "smartwatch-abc123",
  "credit_balance": 147,
  "reward_tier": "silver",
  "streak_days": 5,
  "cumulative_credits_earned": 642,
  "cumulative_credits_spent": 58,
  "next_tier": "gold",
  "credits_to_next_tier": 858,
  "tier_multiplier": 1.25,
  "tier_discount": 0.0
}
```

`next_tier` and `credits_to_next_tier` are `null` when device is already Platinum.

**Response 404**: `{"detail": "Device 'xyz' not found"}`

---

## GET /api/v1/devices/{device_id}/credits/transactions

Paginated credit transaction history for a device, newest first.

**Query params**:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)
- `action_type` (optional filter, e.g. `activity_reward`)

**Response 200**:
```json
{
  "device_id": "smartwatch-abc123",
  "total": 87,
  "limit": 50,
  "offset": 0,
  "transactions": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "amount": 12,
      "action_type": "activity_reward",
      "resulting_balance": 147,
      "reason": "workout activity reward (silver multiplier 1.25×)",
      "metadata": {
        "event_id": "evt-001",
        "scenario": "workout",
        "base_amount": 10,
        "multiplier": 1.25
      },
      "created_at": "2026-05-04T09:43:11Z"
    }
  ]
}
```

---

## POST /api/v1/devices/{device_id}/credits (extended)

Manual credit top-up. Existing endpoint — extended with optional `reason` field.

**Request body**:
```json
{
  "amount": 50,
  "reason": "monthly platform credit allocation"
}
```

`reason` defaults to `"manual top-up"` if omitted.

**Response 200**:
```json
{
  "device_id": "smartwatch-abc123",
  "credit_balance": 197,
  "reward_tier": "silver"
}
```

---

## Frontend API (React SPA)

The React frontend communicates with the backend via the above REST endpoints using `X-API-Key` stored in browser `sessionStorage` (entered via a login form). All requests include `Content-Type: application/json`.

CORS is already enabled on the FastAPI backend (`allow_origins=["*"]` in PoC; tightened in production).

The Vite dev proxy routes `/api/*` → `http://localhost:8100` to avoid CORS friction during development.
