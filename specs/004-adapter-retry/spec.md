# Feature Specification: Recommendation Provider Retry Mechanism

**Feature Branch**: `004-adapter-retry`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Implement retry mechanism for calling recommendation services (src/recommendation/adapters). If a call to a service failed we should have 3 retries with the same data. After 3 unsuccessful retries produce a log message with the error (http status, endpoint, service name)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transient Failures Are Retried Transparently (Priority: P1)

A device requests personalised recommendations. One of the provider services returns an error (network timeout, HTTP 5xx, connection refused). The platform retries the call up to 3 times before giving up. The device still receives a valid recommendation response as long as at least one provider eventually succeeds or another provider responds successfully.

**Why this priority**: Transient failures are the most common cause of provider unavailability. Without retry, a momentary blip causes an unnecessary provider failure that degrades recommendation quality. This is the core value of the feature.

**Independent Test**: Can be fully tested by mocking a provider to fail N times then succeed, and verifying the device receives valid recommendations.

**Acceptance Scenarios**:

1. **Given** a provider fails on the first call with an HTTP 500, **When** the platform retries, **Then** the provider is called again with identical request data up to 3 additional times.
2. **Given** a provider fails twice then succeeds on the third attempt, **When** the recommendation request completes, **Then** the device receives a valid recommendation list and no error is reported for that provider.
3. **Given** a provider succeeds on the first call, **When** the recommendation request completes, **Then** no retries are made and the response is returned immediately.

---

### User Story 2 - Persistent Failures Are Logged with Full Context (Priority: P2)

A provider service is genuinely down. After 3 retries all fail. An operator monitoring the platform can see a structured log entry identifying exactly which provider failed, what endpoint was called, and what the HTTP status code was on each attempt.

**Why this priority**: Observability of persistent failures is essential for on-call operators to diagnose provider outages quickly. Without this, a silent failure leaves no actionable signal.

**Independent Test**: Can be fully tested by mocking a provider to fail all 3 retries and asserting the log output contains provider name, endpoint URL, and HTTP status.

**Acceptance Scenarios**:

1. **Given** a provider fails all 3 retry attempts, **When** the final attempt fails, **Then** a log message at ERROR level is emitted containing: provider name, endpoint URL, HTTP status code of the last failure, and total number of attempts made.
2. **Given** a provider times out on all 3 retry attempts (no HTTP status), **When** the final attempt fails, **Then** the log message records the error type (e.g. "timeout") in place of HTTP status.
3. **Given** all 3 retries are exhausted, **When** the log message is emitted, **Then** the provider still produces an empty result (graceful degradation continues — no exception propagates out of the adapter).

---

### User Story 3 - Retry Behaviour Is Consistent Across All Adapters (Priority: P3)

The retry logic applies uniformly to Service1, Service2, Service3, and all dynamically registered providers. An operator does not need to configure retries per-provider — the behaviour is the same everywhere.

**Why this priority**: Consistency prevents gaps where one adapter silently fails without retry while another retries. Uniform behaviour reduces cognitive overhead when diagnosing incidents.

**Independent Test**: Can be verified by inspecting each adapter or their shared base implementation to confirm the same retry count and logging logic applies.

**Acceptance Scenarios**:

1. **Given** any of Service1, Service2, Service3, or a dynamic provider fails, **When** the call is retried, **Then** the same 3-retry policy and logging behaviour applies regardless of which adapter is invoked.

---

### Edge Cases

- What happens when a provider returns HTTP 4xx (client error such as 400 Bad Request)? — These indicate a problem with the request data itself; retrying with the same data is unlikely to succeed. Assumption: 4xx responses are treated as immediate failures (no retry) and counted as a single failed attempt.
- What happens if the provider fails partway through a retry sequence and then the whole request times out? — The per-provider `asyncio.wait_for` timeout governs the total wall time; each retry attempt is bounded by a fraction of that budget.
- What happens when all providers exhaust their retries? — Existing `AllProvidersFailedError` (HTTP 503) behaviour is preserved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST retry a failed provider call up to 3 times before marking that provider as failed.
- **FR-002**: Each retry attempt MUST use the same request data (height, weight, and all derived fields) as the original call.
- **FR-003**: The system MUST NOT retry calls that fail with an HTTP 4xx client error, as the same data will not produce a different outcome.
- **FR-004**: After all retry attempts are exhausted, the system MUST emit a structured log message at ERROR level containing: provider name, endpoint URL, HTTP status code (or error type if no HTTP response), and number of attempts made.
- **FR-005**: The retry mechanism MUST apply to all provider adapters: Service1, Service2, Service3, and any dynamically registered provider.
- **FR-006**: A provider that eventually succeeds within its retry budget MUST NOT produce an error log message.
- **FR-007**: The retry mechanism MUST NOT change the graceful-degradation behaviour — exhausting retries still results in an empty `ProviderResult`, not a raised exception.

### Key Entities

- **Provider Adapter**: An adapter that calls an external recommendation API. Has a `provider_id`, an endpoint URL, and a `get_recommendations` method.
- **Retry Attempt**: A single call to a provider's endpoint. Up to 4 total calls may be made (1 original + 3 retries).
- **Provider Result**: The outcome of a provider call — either a list of recommendations or an empty list with an error field.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A provider that fails once but succeeds on retry contributes its recommendations to the final response in 100% of such cases.
- **SC-002**: Every persistent provider failure (all retries exhausted) produces exactly one ERROR-level log entry containing provider name, endpoint, and failure reason.
- **SC-003**: The additional retry attempts do not increase the overall recommendation request latency beyond the existing per-provider timeout budget.
- **SC-004**: The retry logic is covered by automated tests that verify both the retry count and the log output, achieving the project's 80% coverage threshold.

## Assumptions

- Retries are applied at the individual adapter level, not at the aggregator level — each provider manages its own retry budget independently.
- The existing per-provider `asyncio.wait_for` timeout applies to the entire retry sequence, not per attempt. This keeps worst-case latency bounded without requiring a separate per-attempt timeout configuration.
- HTTP 4xx errors are not retried (retrying with identical data against a client-error response is pointless and could cause rate limiting).
- No delay (backoff) is introduced between retry attempts in this iteration — the feature is scoped to basic retry count and logging only.
- The retry count of 3 is fixed and not configurable at runtime in this iteration.
