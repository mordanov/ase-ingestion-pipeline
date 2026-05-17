# Implementation Plan: Recommendation Provider Retry Mechanism

**Branch**: `004-adapter-retry` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/004-adapter-retry/spec.md`

## Summary

Add a 3-retry policy to all recommendation provider adapters so that transient HTTP 5xx errors and network failures are automatically retried with the same request data. After all retries are exhausted a structured ERROR log is emitted containing provider name, endpoint URL, HTTP status (or error type), and attempt count. The public `ProviderAdapter` contract and graceful-degradation behaviour are unchanged.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: httpx (async HTTP client), asyncio, structlog
**Storage**: N/A — retry is stateless, in-memory logic only
**Testing**: pytest, pytest-asyncio, unittest.mock.AsyncMock
**Target Platform**: Linux server (Docker container)
**Project Type**: web-service
**Performance Goals**: No additional latency on success paths; worst-case bounded by existing 800ms per-provider `asyncio.wait_for` timeout
**Constraints**: Retry logic must not propagate exceptions out of any adapter; 4xx responses must not be retried
**Scale/Scope**: 4 adapters affected (Service1, Service2, Service3, DynamicAdapter)

## Constitution Check

Constitution template is not yet filled in for this project. No gates to evaluate.
No complexity violations — this feature adds a utility function and modifies 4 call sites. No new abstractions, no new services, no schema changes.

## Project Structure

### Documentation (this feature)

```text
specs/004-adapter-retry/
├── plan.md              ← this file
├── research.md          ← Phase 0 complete
├── data-model.md        ← Phase 1 complete
├── contracts/
│   └── provider-adapter.md   ← Phase 1 complete
└── tasks.md             ← Phase 2 output (/speckit-tasks)
```

### Source Code

```text
src/recommendation/
├── retry.py                          ← NEW: post_with_retry utility
├── adapters/
│   ├── service1_adapter.py           ← MODIFY: use post_with_retry
│   ├── service2_adapter.py           ← MODIFY: use post_with_retry
│   ├── service3_adapter.py           ← MODIFY: use post_with_retry in both schema methods
│   └── dynamic_adapter.py            ← MODIFY: use post_with_retry
└── interfaces.py                     ← unchanged

tests/unit/
└── test_retry.py                     ← NEW: unit tests for post_with_retry + adapter behaviour
```

## Implementation Detail

### New file: `src/recommendation/retry.py`

```python
import httpx
from src.observability.logging import get_logger

logger = get_logger(__name__)

async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_body: dict,
    provider_id: str,
    max_retries: int = 3,
) -> httpx.Response | None:
    last_status: int | None = None
    last_error: str | None = None

    for attempt in range(1, max_retries + 2):   # 1 … max_retries+1 inclusive
        try:
            resp = await client.post(url, json=json_body)
            if resp.status_code < 500:           # 2xx / 3xx / 4xx → return immediately
                return resp
            last_status = resp.status_code       # 5xx → will retry
        except Exception as exc:
            last_error = str(exc)

        if attempt <= max_retries:               # still have retries left
            continue

    # All attempts exhausted
    logger.error(
        "provider_retries_exhausted",
        provider=provider_id,
        endpoint=url,
        http_status=last_status,
        error=last_error,
        attempts=max_retries + 1,
    )
    return None
```

### Adapter changes (same pattern for all four)

Replace the bare `await self._client.post(url, json=body)` call with `await post_with_retry(self._client, url, body, self.provider_id)`. When `None` is returned, produce an empty `ProviderResult(error="retries_exhausted")`.

**Service1** (`get_recommendations`):
```python
# before
resp = await self._client.post(self._endpoint, json={...})

# after — build body first so the same dict is used on every retry
req_body = {"height": height_cm, "weight": weight_kg, "token": self._token}
resp = await post_with_retry(self._client, self._endpoint, req_body, self.provider_id)
if resp is None:
    return ProviderResult(provider_id=self.provider_id, recommendations=[],
                          duration_ms=int((time.monotonic() - start) * 1000),
                          error="retries_exhausted")
```

**Service2** (`get_recommendations`):
- Generate `session_token = str(uuid.uuid4())` **before** calling `post_with_retry` so the same token is reused across retries.

**Service3** (`_call_service1_schema` and `_call_service2_schema`):
- Same pattern applied to both internal call methods.
- In `_call_service2_schema`, generate `session_token` before the retry call.

**DynamicAdapter** (`get_recommendations`):
- `req_body = self._build_request(height_cm, weight_kg)` already builds the body once; just replace the `client.post` call.

### Test coverage requirements

`tests/unit/test_retry.py` must cover:

1. **Success on first attempt** — `post_with_retry` returns the response, no retry.
2. **Success on second attempt (1 retry)** — first call raises exception, second succeeds.
3. **Success on fourth attempt (3 retries)** — fails 3 times, succeeds on final attempt.
4. **Exhaustion after 4 attempts** — all 4 calls fail with 5xx; returns `None`; logger.error called once with correct fields.
5. **4xx not retried** — returns response immediately after first 4xx; no further calls.
6. **Error log fields** — asserts `provider`, `endpoint`, `http_status`, `attempts` in log call.
7. **Adapter integration** — at least one adapter (e.g. Service1) tested end-to-end: mock HTTP to fail twice then succeed → valid `ProviderResult` returned.
