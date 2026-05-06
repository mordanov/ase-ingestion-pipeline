# Recommendation Aggregation

Every call to `POST /api/v1/devices/{id}/recommendations` fans out to multiple external provider APIs **in parallel**, normalises their responses to a common format, deduplicates overlapping items, and returns a single ranked list. The ML re-ranking layer then re-orders that list before it reaches the device.

---

## Request Flow

```
Device
  │
  ▼
POST /api/v1/devices/{id}/recommendations
  │
  ├─ Credit check (402 if balance = 0)
  ├─ Disabled check (403 if on blocklist)
  │
  ▼
aggregate(providers, height_cm, weight_kg, timeout=0.8s)
  │
  ├─ asyncio.gather ──▶ Service1Adapter.get_recommendations()
  │                ──▶ Service2Adapter.get_recommendations()
  │                ──▶ Service3Adapter.get_recommendations()   (if SERVICE3_ENDPOINT set)
  │                ──▶ DynamicAdapter × N                      (active rows in provider_schemas)
  │
  │  each call wrapped in asyncio.wait_for(timeout=0.8 s)
  │  timeout / error → empty result, logged; does NOT fail the whole request
  │
  ▼
group_and_sort(all_raw_recs, min_score=min_confidence*1000)
  │  deduplicate by normalised text, keep max score per group, sort descending
  │
  ▼
ML layer  (re-ranking + anomaly suppression)
  │
  ▼
RecommendationResponse → device
```

If **all** providers fail or time out → `503 AllProvidersFailedError`. If at least one succeeds, the request returns 200 regardless of which others failed (`providers_called` vs `providers_succeeded` in the response tells you which).

---

## Built-in Providers

### Service 1

**Request format** (metric units, token auth):
```json
{ "height": 175.0, "weight": 72.0, "token": "<SERVICE1_TOKEN>" }
```

**Response format** — array of objects:
```json
[
  { "recommendation": "Go for a brisk walk", "confidence": 0.87 },
  ...
]
```
Score normalisation: `confidence × 1000` → internal scale 0–1000.

Also handles Lambda proxy envelope: if the response has `{ "statusCode": ..., "body": "..." }` the body string is JSON-parsed automatically.

---

### Service 2

**Request format** (imperial units, fresh session token):
```json
{
  "measurements": { "mass": 158.73, "height": 5.7415 },
  "birth_date": 631152000,
  "session_token": "<random-uuid>"
}
```
Height is converted cm→feet, weight kg→lbs before sending. `birth_date` defaults to 1990-01-01 (PoC placeholder).

**Response format** — array (or `{ "recommendations": [...] }`):
```json
[
  { "title": "Increase daily steps", "priority": 850, "details": "Aim for 8,000 steps." },
  ...
]
```
Score normalisation: `priority` is already on the 0–1000 scale; used as-is.

---

## Deduplication & Ranking

`group_and_sort()` merges results from all providers into a single list:

1. **Normalise text key** — strip punctuation, lowercase, trim.
2. **Group** — items whose normalised text matches are merged into one entry.
3. **Keep max score** — if Service1 and Service2 both recommend "drink more water" with scores 700 and 820, the merged item carries score 820 and `providers: ["service1", "service2"]`.
4. **Filter** — items below `min_score` (`min_confidence × 1000`, default 200) are dropped.
5. **Sort** — descending by score.

The `providers` list in the response tells the device (and the dashboard) which sources agreed on each item.

---

## Onboarding a New Provider

There are two ways to add a provider.

### Option A — Dynamic provider (no code, at runtime)

Register via the API — no deployment needed:

```http
POST /api/v1/provider-schemas
X-API-Key: <key>

{
  "name": "my-new-service",
  "endpoint_url": "https://api.example.com/v1/recommend",
  "request_mapping": {
    "fields": {
      "user.height_cm":    "$HEIGHT",
      "user.weight_kg":    "$WEIGHT",
      "api_key":           "$CONST:my-secret-key",
      "request_id":        "$UUID"
    }
  },
  "response_mapping": {
    "array_path":       "data.recommendations",
    "text_field":       "advice",
    "score_field":      "score",
    "score_multiplier": 10,
    "detail_field":     "explanation"
  },
  "is_active": true
}
```

The record is persisted to the `provider_schemas` PostgreSQL table. On the **next** recommendation request, `DynamicAdapter` is instantiated from that row and included in the fan-out — no restart required.

**`request_mapping.fields`** — map each dot-notation JSON path in the request body to an expression:

| Expression | Value sent |
|---|---|
| `$HEIGHT` | patient height in cm |
| `$HEIGHT_FT` | height converted to feet |
| `$WEIGHT` | patient weight in kg |
| `$WEIGHT_LBS` | weight converted to lbs |
| `$UUID` | random UUID per request |
| `$CONST:value` | literal string, int, or float |

**`response_mapping`** — tells the adapter how to extract items from the response:

| Field | Description |
|---|---|
| `array_path` | dot-notation path to the array; `""` = root is the array |
| `text_field` | key containing the recommendation text |
| `score_field` | key containing the numeric score |
| `score_multiplier` | multiply raw score by this factor to bring it to the 0–1000 scale |
| `detail_field` | optional key for extended detail text |

Disable a dynamic provider without deleting it:
```http
PUT /api/v1/provider-schemas/{id}
{ "is_active": false }
```

---

### Option B — Static adapter (code change, for complex providers)

Use this when the provider has an unusual auth scheme, non-JSON transport, pagination, or other logic that doesn't fit the mapping model.

1. Create `src/recommendation/adapters/my_service_adapter.py`:
   ```python
   from src.recommendation.interfaces import ProviderAdapter, ProviderResult, RawRecommendation

   class MyServiceAdapter(ProviderAdapter):
       provider_id = "my-service"

       def __init__(self, http_client, endpoint, api_key):
           self._client = http_client
           self._endpoint = endpoint
           self._api_key = api_key

       async def get_recommendations(self, height_cm, weight_kg) -> ProviderResult:
           # build request, call API, parse response
           # return ProviderResult(provider_id=self.provider_id, recommendations=[...], duration_ms=...)
           ...
   ```
   The only contract is `get_recommendations(height_cm, weight_kg) → ProviderResult`. Errors should be caught internally and returned as `ProviderResult(error="...")` — never raised, so a single bad provider never fails the whole request.

2. Register it in `src/api/dependencies.py` → `get_provider_adapters()`:
   ```python
   if settings.my_service_endpoint:
       adapters.append(MyServiceAdapter(http_client, settings.my_service_endpoint, settings.my_service_key))
   ```

3. Add the corresponding env vars to `Settings` and `.env.example`.

4. Deploy. The new adapter is picked up on startup.

---

## Timeout & Resilience

| Behaviour | Detail |
|---|---|
| Per-provider timeout | 800 ms default (`RECOMMENDATION_TIMEOUT_SECONDS`) |
| Timeout handling | Returns empty `ProviderResult(error="timeout")`, logged as warning |
| Exception handling | Any unhandled exception also returns empty result, logged as error |
| All-fail gate | If zero providers succeed → `503` with `providers_attempted` list |
| One-fail tolerance | Any subset of providers can fail; remaining results are aggregated normally |

The timeout applies independently to each provider — a slow Service2 does not delay Service1's items.
