# Tasks: Recommendation Provider Retry Mechanism

**Input**: Design documents from `specs/004-adapter-retry/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new module and establish test file; no logic yet.

- [x] T001 Create empty module `src/recommendation/retry.py` with module docstring
- [x] T002 [P] Create empty test file `tests/unit/test_retry.py` with imports for `post_with_retry`

**Checkpoint**: Files exist, imports resolve cleanly — `python -c "from src.recommendation.retry import post_with_retry"` succeeds after T001 defines the function signature.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement the core `post_with_retry` function signature and no-op stub so all adapters can integrate against a stable interface before logic is filled in.

**⚠️ CRITICAL**: All user story phases depend on this signature being stable.

- [x] T003 Implement `post_with_retry(client, url, json_body, provider_id, max_retries=3) -> httpx.Response | None` stub in `src/recommendation/retry.py` — returns `await client.post(url, json=json_body)` with no retry yet, just a working signature

**Checkpoint**: Foundation ready — all adapters can call `post_with_retry` and receive a valid response (single-attempt behaviour). User story phases can now begin.

---

## Phase 3: User Story 1 — Transient Failures Are Retried Transparently (Priority: P1) 🎯 MVP

**Goal**: A provider that fails with 5xx or a network exception is retried up to 3 times. If it succeeds within the retry budget the device receives valid recommendations. 4xx responses are not retried.

**Independent Test**: Mock Service1's HTTP client to fail once (5xx) then succeed; assert `get_recommendations` returns a non-empty `ProviderResult` with no error field.

### Tests for User Story 1

> Write and confirm these tests **FAIL** before implementing T007.

- [x] T004 [P] [US1] Write test `test_success_on_first_attempt` in `tests/unit/test_retry.py` — mock client.post returning 200; assert `post_with_retry` returns response and `client.post` called exactly once
- [x] T005 [P] [US1] Write test `test_retry_on_5xx_then_success` in `tests/unit/test_retry.py` — mock client.post to return 503 twice then 200; assert response returned and `client.post` called 3 times
- [x] T006 [P] [US1] Write test `test_no_retry_on_4xx` in `tests/unit/test_retry.py` — mock client.post returning 400; assert response returned immediately and `client.post` called exactly once

### Implementation for User Story 1

- [x] T007 Implement retry loop in `post_with_retry` in `src/recommendation/retry.py`: loop `max_retries + 1` times; return immediately on 2xx/3xx/4xx; on 5xx or exception record `last_status`/`last_error` and continue; return `None` after exhaustion (logging added in US2)
- [x] T008 [US1] Integrate `post_with_retry` into `Service1Adapter.get_recommendations` in `src/recommendation/adapters/service1_adapter.py`: build `req_body` dict before the call; replace `await self._client.post(...)` with `await post_with_retry(...)`; handle `None` return as `ProviderResult(error="retries_exhausted")`
- [x] T009 [P] [US1] Write integration-style test `test_service1_retries_on_transient_failure` in `tests/unit/test_retry.py` — mock httpx client injected into Service1Adapter; fail once 500 then succeed; assert non-empty ProviderResult returned

**Checkpoint**: User Story 1 is fully functional — Service1 retries transient failures silently. All T004–T006, T009 tests pass.

---

## Phase 4: User Story 2 — Persistent Failures Are Logged with Full Context (Priority: P2)

**Goal**: When all retry attempts are exhausted, one ERROR log entry is emitted with `provider`, `endpoint`, `http_status`, `error`, and `attempts` fields.

**Independent Test**: Mock Service1's HTTP client to fail all 4 attempts; assert exactly one `logger.error` call with the correct structured fields.

### Tests for User Story 2

> Write and confirm these tests **FAIL** before implementing T011.

- [x] T010 [P] [US2] Write test `test_exhaustion_emits_error_log` in `tests/unit/test_retry.py` — mock client.post always returning 503; patch logger; assert `logger.error` called once with `provider`, `endpoint`, `http_status=503`, `attempts=4`
- [x] T010b [P] [US2] Write test `test_exhaustion_on_network_error_emits_log` in `tests/unit/test_retry.py` — mock client.post always raising `httpx.ConnectError`; patch logger; assert `logger.error` called once with `http_status=None` and non-None `error` field
- [x] T010c [P] [US2] Write test `test_no_log_on_eventual_success` in `tests/unit/test_retry.py` — mock client.post failing twice then succeeding; patch logger; assert `logger.error` never called

### Implementation for User Story 2

- [x] T011 [US2] Add exhaustion log to `post_with_retry` in `src/recommendation/retry.py`: after the loop exits with `None`, call `logger.error("provider_retries_exhausted", provider=provider_id, endpoint=url, http_status=last_status, error=last_error, attempts=max_retries + 1)`

**Checkpoint**: User Story 2 complete — exhaustion always produces exactly one structured ERROR log. All T010–T010c tests pass.

---

## Phase 5: User Story 3 — Retry Behaviour Is Consistent Across All Adapters (Priority: P3)

**Goal**: Service2, Service3 (both schema variants), and DynamicAdapter use `post_with_retry` with the same 3-retry policy as Service1.

**Independent Test**: Run each adapter with a mock client that fails twice then succeeds; verify all four return a non-empty ProviderResult.

### Tests for User Story 3

- [x] T012 [P] [US3] Write test `test_service2_retries_on_transient_failure` in `tests/unit/test_retry.py` — mock httpx client in Service2Adapter; fail 500 twice then 200; assert non-empty ProviderResult; assert same session_token used in all calls (UUID not regenerated per retry)
- [x] T013 [P] [US3] Write test `test_dynamic_adapter_retries_on_transient_failure` in `tests/unit/test_retry.py` — mock httpx client in DynamicAdapter; fail once then succeed; assert non-empty ProviderResult

### Implementation for User Story 3

- [x] T014 [P] [US3] Integrate `post_with_retry` into `Service2Adapter.get_recommendations` in `src/recommendation/adapters/service2_adapter.py`: generate `session_token = str(uuid.uuid4())` before building `json_body`; replace `await self._client.post(...)` with `await post_with_retry(...)`; handle `None` return
- [x] T015 [P] [US3] Integrate `post_with_retry` into `Service3Adapter._call_service1_schema` and `_call_service2_schema` in `src/recommendation/adapters/service3_adapter.py`: in `_call_service2_schema` generate `session_token` before the call; replace both `await self._client.post(...)` calls; handle `None` return in both methods
- [x] T016 [P] [US3] Integrate `post_with_retry` into `DynamicAdapter.get_recommendations` in `src/recommendation/adapters/dynamic_adapter.py`: `req_body` is already built by `_build_request` before the call; replace `await self._client.post(...)` with `await post_with_retry(...)`; handle `None` return

**Checkpoint**: All four adapters retry consistently. T012–T013 tests pass.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T017 [P] Verify 80% test coverage threshold still met — run `pytest tests/unit/test_retry.py --cov=src/recommendation/retry --cov=src/recommendation/adapters` and confirm no regressions
- [x] T018 [P] Remove any per-adapter `logger.error` calls that duplicate the new exhaustion log in `src/recommendation/adapters/` (e.g. `service1_error`, `service2_error` log calls on the outer except that are now superseded by `post_with_retry`'s logging)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001 and T002 are parallel
- **Foundational (Phase 2)**: Depends on T001 — BLOCKS all user story phases
- **US1 (Phase 3)**: Depends on T003 — tests (T004–T006) can be written in parallel with T003; T007 depends on T003; T008 depends on T007; T009 depends on T008
- **US2 (Phase 4)**: Depends on T007 (retry loop must exist to test exhaustion); T011 depends on T007
- **US3 (Phase 5)**: Depends on T003; T014–T016 can run in parallel with each other; T012–T013 can be written before T014–T016
- **Polish (Phase 6)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2 — no dependency on other stories
- **US2 (P2)**: Depends on US1's T007 (retry loop) — can begin writing tests in parallel with US1 implementation
- **US3 (P3)**: Depends on Phase 2 only — can proceed in parallel with US1/US2 once `post_with_retry` signature is stable

### Parallel Opportunities

- T001 and T002 (Phase 1) are fully parallel
- T004, T005, T006 (US1 tests) can be written in parallel with each other and with T007 implementation
- T010, T010b, T010c (US2 tests) can be written in parallel
- T014, T015, T016 (US3 adapter changes) are fully parallel — different files
- T012, T013 (US3 tests) are parallel with each other

---

## Parallel Example: User Story 3

```
# All adapter integrations are independent files — run together:
Task T014: src/recommendation/adapters/service2_adapter.py
Task T015: src/recommendation/adapters/service3_adapter.py
Task T016: src/recommendation/adapters/dynamic_adapter.py

# All US3 tests are independent:
Task T012: test_service2_retries_on_transient_failure
Task T013: test_dynamic_adapter_retries_on_transient_failure
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003)
3. Write US1 tests (T004–T006) — confirm they fail
4. Implement retry loop (T007)
5. Integrate into Service1 (T008)
6. Write integration test (T009)
7. **STOP and VALIDATE**: Service1 silently retries transient failures

### Incremental Delivery

1. Setup + Foundational → stub `post_with_retry` in place
2. US1 complete → Service1 retries, tested
3. US2 complete → exhaustion logging, tested
4. US3 complete → all four adapters consistent
5. Polish → coverage verified, duplicate logs removed

---

## Notes

- `session_token` (UUID) in Service2 and Service3-schema2 must be generated **before** the retry loop — do not regenerate per attempt
- `post_with_retry` returns `httpx.Response | None`; each adapter handles `None` by returning `ProviderResult(recommendations=[], error="retries_exhausted")`
- The outer `asyncio.wait_for` timeout in the aggregator bounds the whole retry sequence — no per-attempt timeout needed
- Existing `logger.error("service1_error", ...)` calls in the outer `except` of each adapter may be removed in T018 to avoid duplicate log noise
