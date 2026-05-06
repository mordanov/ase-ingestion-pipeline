# Contract: ProviderAdapter

The `ProviderAdapter` interface contract is **unchanged** by this feature.

```python
class ProviderAdapter(ABC):
    provider_id: str

    @abstractmethod
    async def get_recommendations(self, height_cm: float, weight_kg: float) -> ProviderResult:
        """Fetch and normalise recommendations from an external provider.
        
        - MUST return ProviderResult in all cases — never raise.
        - On persistent failure (all retries exhausted), returns ProviderResult with
          recommendations=[] and error set to a non-None string.
        - duration_ms covers total elapsed time including all retry attempts.
        """
```

## What changes internally (not part of the public contract)

The concrete adapter implementations call the new `post_with_retry` utility instead of calling `client.post` directly. This is an implementation detail — callers (the aggregator) observe no change in behaviour except that transient failures are less likely to result in an empty result.

## post_with_retry utility contract

```python
async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_body: dict,
    provider_id: str,
    max_retries: int = 3,
) -> httpx.Response | None:
    """POST json_body to url with up to max_retries retries on 5xx / network errors.

    Returns:
      - httpx.Response on success (2xx) or client error (4xx) — caller checks status code.
      - None if all attempts are exhausted; an ERROR log is emitted before returning None.

    Never raises. All exceptions are caught internally.
    """
```
