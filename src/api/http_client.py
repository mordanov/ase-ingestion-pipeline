import httpx

_http_client: httpx.AsyncClient | None = None


def init_http_client(timeout_seconds: float = 1.5) -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
    return _http_client


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialised")
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
