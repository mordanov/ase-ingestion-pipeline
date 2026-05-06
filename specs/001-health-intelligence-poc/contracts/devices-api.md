# Contract: Devices API

**Base path**: `/api/v1/devices`
**Auth**: API key header `X-API-Key` (configured via `API_KEY` env var)

---

## POST /api/v1/devices — Register Device

Creates a new device record and its corresponding digital-twin entry in AWS IoT Core (or the
local registry adapter in dev). Idempotent on `device_id` — returns existing record if already
registered.

### Request

```json
{
  "device_id": "smartwatch-a3f9b2c1",
  "device_type": "smartwatch",
  "model": "FunWatch Pro 3",
  "firmware_version": "2.2.3",
  "os": "WearOS 3.2",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "height_cm": 184.0,
  "weight_kg": 84.0
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `device_id` | Yes | Must match simulator's device_id / cert CN |
| `device_type` | Yes | `smartwatch` \| `fitness_tracker` \| `smartphone` \| `laptop` |
| `model` | Yes | Hardware model string |
| `firmware_version` | Yes | Semver string |
| `os` | Yes | OS name + version |
| `user_id` | Yes | UUID — PII, not logged |
| `height_cm` | Yes | Stored for provider enrichment; not returned in API responses |
| `weight_kg` | Yes | Stored for provider enrichment; not returned in API responses |

### Response — 201 Created (new) / 200 OK (idempotent)

```json
{
  "device_id": "smartwatch-a3f9b2c1",
  "device_type": "smartwatch",
  "model": "FunWatch Pro 3",
  "firmware_version": "2.2.3",
  "os": "WearOS 3.2",
  "credit_balance": 100,
  "reward_tier": "bronze",
  "iot_thing_name": "smartwatch-a3f9b2c1",
  "registered_at": "2026-05-04T10:00:00Z"
}
```

**Note**: `height_cm` and `weight_kg` are NOT returned in any API response (PII minimisation).
`credit_balance` is initialised to 100 on first registration.

### Response — 422 Unprocessable Entity

```json
{
  "detail": [
    { "loc": ["body", "height_cm"], "msg": "field required", "type": "missing" }
  ]
}
```

---

## GET /api/v1/devices/{device_id} — Get Device Twin State

Returns current device state including live credit balance, reward tier, and IoT twin shadow
state (last seen timestamp from IoT Core).

### Response — 200 OK

```json
{
  "device_id": "smartwatch-a3f9b2c1",
  "device_type": "smartwatch",
  "model": "FunWatch Pro 3",
  "firmware_version": "2.2.3",
  "os": "WearOS 3.2",
  "credit_balance": 87,
  "reward_tier": "bronze",
  "cumulative_credits_spent": 13,
  "iot_thing_name": "smartwatch-a3f9b2c1",
  "twin_last_seen": "2026-05-04T10:12:00Z",
  "twin_connected": true,
  "registered_at": "2026-05-04T10:00:00Z",
  "updated_at": "2026-05-04T10:12:00Z"
}
```

### Response — 404 Not Found

```json
{ "detail": "Device smartwatch-a3f9b2c1 not found" }
```

---

## POST /api/v1/devices/{device_id}/credits — Top Up Credits

Adds credits to a device balance. Creates a `top_up` CreditTransaction.

### Request

```json
{ "amount": 500 }
```

### Response — 200 OK

```json
{
  "device_id": "smartwatch-a3f9b2c1",
  "added": 500,
  "new_balance": 587,
  "reward_tier": "bronze"
}
```
