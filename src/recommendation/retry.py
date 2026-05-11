"""HTTP retry utility for recommendation provider adapters."""

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
    """POST json_body to url with up to max_retries retries on 5xx / network errors.

    Returns an httpx.Response on success (2xx/3xx) or on a client error (4xx) —
    the caller is responsible for checking the status code.
    Returns None if all attempts are exhausted; logs ERROR before returning.

    Never raises. All exceptions are caught internally.
    4xx responses are returned immediately without retry.
    """
    last_status: int | None = None
    last_error: str | None = None

    for attempt in range(1, max_retries + 2):  # 1 … max_retries+1 inclusive (4 total)
        try:
            resp = await client.post(url, json=json_body)
            if resp.status_code < 500:  # 2xx / 3xx / 4xx — return immediately
                return resp
            last_status = resp.status_code  # 5xx — record and retry
        except Exception as exc:
            last_error = str(exc)

        if attempt <= max_retries:
            continue

    logger.error(
        "provider_retries_exhausted",
        provider=provider_id,
        endpoint=url,
        http_status=last_status,
        error=last_error,
        attempts=max_retries + 1,
    )
    return None
