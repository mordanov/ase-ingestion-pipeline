# Data Model: Recommendation Provider Retry Mechanism

No new persistent data entities are introduced by this feature. The retry logic is entirely in-memory and stateless.

## Existing Entities (unchanged)

### ProviderResult
The public return type of every adapter. Shape is unchanged — retry exhaustion still produces an empty `ProviderResult(error=...)`, not a new type.

```
ProviderResult
  provider_id : str         — which provider produced this result
  recommendations : list    — empty on failure
  duration_ms : int         — wall time of the full call (including retries)
  error : str | None        — set on failure; None on success
```

### RawRecommendation
Unchanged. Only populated when at least one attempt succeeds.

## New Runtime State (in-memory only)

### RetryContext (not persisted)
Transient state held inside `post_with_retry` for the duration of a single adapter call:

```
attempt_count : int         — increments from 1 to max_attempts (4 total: 1 original + 3 retries)
last_http_status : int|None — HTTP status of the most recent failed response; None on network error
last_error : str|None       — exception message of the most recent network/parse error
```

These fields are used only to produce the final log message and are discarded after the function returns.

## State Transitions

```
Initial call
    │
    ▼
attempt_count = 1
    │
    ├─ HTTP 2xx/3xx ──────────────────────────────▶ return Response (success)
    │
    ├─ HTTP 4xx ──────────────────────────────────▶ return Response (client error, no retry)
    │
    ├─ HTTP 5xx / network exception
    │     attempt_count < max_attempts ──────────▶ attempt_count += 1, retry
    │     attempt_count == max_attempts ─────────▶ log ERROR, return None
    │
    ▼
caller receives None → adapter returns empty ProviderResult(error=...)
```
