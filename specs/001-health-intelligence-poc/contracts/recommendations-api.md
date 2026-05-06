# Contract: Recommendations API

**Base path**: `/api/v1/devices/{device_id}/recommendations`
**Auth**: API key header `X-API-Key`

---

## POST /api/v1/devices/{device_id}/recommendations — Get Aggregated Recommendations

Enriches the request with the device's stored biometric profile, fans out concurrently to all
configured providers (Service1, Service2, Service3) with an 800 ms total timeout, normalises
scores, groups by short recommendation text, filters by minimum confidence, and returns the
sorted aggregated list. Deducts 1 credit from the device balance.

### Request (optional body — overrides stored profile if provided)

```json
{
  "min_confidence": 0.3
}
```

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `min_confidence` | No | `0.2` | Filter threshold (0.0–1.0 normalised) — recommendations below this score are excluded |

### Response — 200 OK

```json
{
  "device_id": "smartwatch-a3f9b2c1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "recommendations": [
    {
      "short_text": "Have more workouts per day",
      "max_score": 750.0,
      "providers": ["service2", "service3"],
      "detail": "Workouts help improving your health."
    },
    {
      "short_text": "Walk more",
      "max_score": 400.0,
      "providers": ["service1"],
      "detail": null
    }
  ],
  "providers_called": ["service1", "service2", "service3"],
  "providers_succeeded": ["service1", "service2", "service3"],
  "duration_ms": 312,
  "credits_remaining": 99,
  "reward_tier": "bronze"
}
```

| Field | Notes |
|-------|-------|
| `recommendations` | Sorted by `max_score` descending; filtered by `min_confidence` |
| `short_text` | Group key — used to merge duplicate recommendations across providers |
| `max_score` | Highest normalised score across all contributing providers for this group. Service1: `confidence × 1000`; Service2/3: `priority` (1–1000) |
| `providers` | Which providers contributed at least one recommendation in this group |
| `providers_called` | All providers attempted |
| `providers_succeeded` | Providers that responded within the 800 ms timeout |
| `duration_ms` | Total aggregation time |
| `credits_remaining` | Balance after this request's deduction |

### Response — 402 Payment Required (zero credits)

```json
{
  "detail": "Insufficient credits",
  "device_id": "smartwatch-a3f9b2c1",
  "credit_balance": 0
}
```

### Response — 503 Service Unavailable (all providers failed)

```json
{
  "detail": "All recommendation providers failed or timed out",
  "trace_id": "...",
  "providers_attempted": ["service1", "service2", "service3"],
  "duration_ms": 801
}
```

**Note on partial results**: If only a subset of providers succeed, the endpoint returns 200
with `providers_succeeded` listing the healthy providers. Partial results are preferable to
failing the entire request when one provider is unavailable.

---

## Normalisation Rules

| Provider | Raw field | Normalised score formula |
|----------|-----------|--------------------------|
| Service1 | `confidence` (0.0–1.0) | `confidence × 1000` |
| Service2 | `priority` (1–1000) | `priority` (used directly) |
| Service3 | TBD (same interface) | Same as Service1 or Service2 per provider config |

**Grouping key**: `short_text` is the `recommendation` field from Service1 and the `title`
field from Service2, normalised to lowercase and stripped of trailing punctuation.

**Merge rule**: When multiple providers return a recommendation with the same group key, the
`max_score` is the maximum normalised score across all sources; `detail` is taken from the
source with the highest score.

---

## Provider Adapter Contracts (internal)

### Service1

- **Endpoint**: `https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service1`
- **Method**: POST
- **Request**: `{ "height": <float cm>, "weight": <float kg>, "token": "service1-dev" }`
- **Success response**: `[ { "confidence": 0.4, "recommendation": "Walk more" }, ... ]`
- **Error response**: `{ "errorCode": 13, "errorMessage": "Invalid user data" }`

### Service2

- **Endpoint**: `https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service2`
- **Method**: POST
- **Request**:
  ```json
  {
    "measurements": { "mass": <float lbs>, "height": <float feet> },
    "birth_date": <unix timestamp UTC>,
    "session_token": "<unique GUID — new per request>"
  }
  ```
  **Unit conversions**: `weight_kg × 2.20462 → lbs`; `height_cm / 30.48 → feet`
  **birth_date**: Not in device profile — use a platform default (e.g. `631152000` = 1990-01-01)
  unless birth date is added to the device registration schema in a future iteration.
- **Success response**: `{ "recommendations": [ { "priority": 750, "title": "...", "details": "..." }, ... ] }`
- **Error response**: `{ "code": 13, "error": "Invalid user data" }`

### Service3

- **Endpoint**: Configurable via `SERVICE3_ENDPOINT` env var
- **Token**: Configurable via `SERVICE3_API_TOKEN` env var (distinct from Service1 and Service2)
- **Protocol**: Same adapter interface as Service1 or Service2; adapter implementation
  determined by `SERVICE3_SCHEMA` env var (`service1_schema` | `service2_schema`)
