# Quickstart: Device Credits Management and Tiered Reward System

**Estimated time**: 10 minutes (assumes docker-compose is already running)

---

## Prerequisites

- Docker Compose stack from Feature 001 is running (`make up`)
- Python virtual environment is active (`.venv`)
- Node.js 20+ installed (for frontend development)
- `make test` passes (51 passed, 3 skipped)

---

## 1. Start the full stack (first time)

```bash
make up      # starts app, postgres, redis, mosquitto, prometheus, grafana, frontend
make migrate # applies DB migrations (002_credits_extended)
make seed    # registers 10 test devices
```

---

## 2. View the credit configuration

```bash
curl -s -H "X-API-Key: ${API_KEY:-dev-key}" \
  http://localhost:8100/api/v1/credit-config | python3 -m json.tool
```

Expected: JSON config showing default activity earning rules, service costs, tier thresholds.

---

## 3. Trigger activity credit earning

Ingest a workout event for a seeded device (copy a device_id from `make seed` output):

```bash
DEVICE_ID="smartwatch-seed-xxxxxxxx"  # replace with actual device_id

curl -s -X POST http://localhost:8100/ingest \
  -H "Content-Type: application/json" \
  -d "{
    \"event_id\": \"$(uuidgen | tr '[:upper:]' '[:lower:]')\",
    \"device_id\": \"$DEVICE_ID\",
    \"device_type\": \"smartwatch\",
    \"user_id\": \"test-user\",
    \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"scenario\": \"workout\",
    \"is_anomaly\": false,
    \"protocol\": \"http\",
    \"firmware_version\": \"1.0.0\",
    \"heart_rate\": {\"bpm\": 145, \"hrv_ms\": 35.0},
    \"spo2\": {\"percentage\": 97.0}
  }"
```

---

## 4. Check the device credit balance

```bash
curl -s -H "X-API-Key: ${API_KEY:-dev-key}" \
  http://localhost:8100/api/v1/devices/$DEVICE_ID/credits | python3 -m json.tool
```

Expected: `credit_balance` increased by ~10 credits (base 10 × bronze multiplier 1.0), `streak_days: 1`.

---

## 5. View transaction history

```bash
curl -s -H "X-API-Key: ${API_KEY:-dev-key}" \
  "http://localhost:8100/api/v1/devices/$DEVICE_ID/credits/transactions?limit=5" \
  | python3 -m json.tool
```

Expected: Latest transaction shows `action_type: "activity_reward"` with `reason: "workout activity reward"`.

---

## 6. Update the credit config (admin)

Increase workout reward to 15 credits:

```bash
curl -s -X PUT http://localhost:8100/api/v1/credit-config \
  -H "X-API-Key: ${API_KEY:-dev-key}" \
  -H "Content-Type: application/json" \
  -d '{
    "default_initial_balance": 100,
    "activity_earning_rules": {"workout": 15, "sport": 8, "sleep": 3, "rest": 2, "default": 2},
    "service_costs": {"service1": 3, "service2": 5, "default": 1},
    "streak_bonus_7d": 5,
    "streak_bonus_30d": 20,
    "tier_thresholds": {"bronze": 0, "silver": 500, "gold": 1500, "platinum": 5000},
    "tier_multipliers": {"bronze": 1.0, "silver": 1.25, "gold": 1.5, "platinum": 2.0},
    "tier_discounts": {"bronze": 0.0, "silver": 0.0, "gold": 0.1, "platinum": 0.2}
  }' | python3 -m json.tool
```

Ingest another workout event and verify the new balance increases by 15 instead of 10.

---

## 7. Open the React admin UI

```
http://localhost:3200
```

- Enter the API key (`dev-key` or from `.env`)
- Search for your `$DEVICE_ID` to see balance, tier badge, and transaction history
- Navigate to Admin → Credit Config to update earning rules via the form

---

## 8. View the Grafana credits dashboard

```
http://localhost:3100  →  Login: admin / (GF_SECURITY_ADMIN_PASSWORD from .env)
Dashboards → Credits & Rewards
```

Panels visible: Credits Balance by Device, Earned vs Spent over time, Tier Distribution, Top Spenders, Streak Leaderboard, Activity Type Breakdown.

---

## 9. Run the tests

```bash
make test
```

Expected: All integration tests for `test_credits_config.py`, `test_activity_earning.py`, and `test_tier_progression.py` pass. Frontend tests run via `make test-frontend`.
