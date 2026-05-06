import time
import uuid

import httpx

from src.observability.logging import get_logger
from src.recommendation.interfaces import ProviderAdapter, ProviderResult, RawRecommendation
from src.recommendation.retry import post_with_retry

logger = get_logger(__name__)

# Default birth_date: 1990-01-01 UTC as unix timestamp
DEFAULT_BIRTH_DATE = 631152000


class Service2Adapter(ProviderAdapter):
    provider_id = "service2"

    def __init__(self, http_client: httpx.AsyncClient, endpoint: str):
        self._client = http_client
        self._endpoint = endpoint

    async def get_recommendations(self, height_cm: float, weight_kg: float) -> ProviderResult:
        start = time.monotonic()
        mass_lbs = round(weight_kg * 2.20462, 4)
        height_feet = round(height_cm / 30.48, 4)
        # Generate session_token once so all retry attempts use the same value
        session_token = str(uuid.uuid4())

        try:
            req_body = {
                "measurements": {"mass": mass_lbs, "height": height_feet},
                "birth_date": DEFAULT_BIRTH_DATE,
                "session_token": session_token,
            }
            resp = await post_with_retry(self._client, self._endpoint, req_body, self.provider_id)
            duration_ms = int((time.monotonic() - start) * 1000)

            if resp is None:
                return ProviderResult(
                    provider_id=self.provider_id,
                    recommendations=[],
                    duration_ms=duration_ms,
                    error="retries_exhausted",
                )

            if resp.status_code != 200:
                return ProviderResult(
                    provider_id=self.provider_id,
                    recommendations=[],
                    duration_ms=duration_ms,
                    error=f"HTTP {resp.status_code}",
                )

            body = resp.json()
            # Unwrap Lambda proxy response envelope if present
            if isinstance(body, dict) and "body" in body and "statusCode" in body:
                import json as _json

                raw = body["body"]
                body = _json.loads(raw) if isinstance(raw, str) else raw

            if isinstance(body, dict) and "code" in body and "error" in body:
                return ProviderResult(
                    provider_id=self.provider_id,
                    recommendations=[],
                    duration_ms=duration_ms,
                    error=body["error"],
                )

            raw_recs = body if isinstance(body, list) else body.get("recommendations", [])
            recs = [
                RawRecommendation(
                    short_text=item["title"],
                    detail=item.get("details"),
                    normalised_score=float(item["priority"]),
                    provider_id=self.provider_id,
                )
                for item in raw_recs
                if "title" in item and "priority" in item
            ]
            return ProviderResult(
                provider_id=self.provider_id, recommendations=recs, duration_ms=duration_ms
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ProviderResult(
                provider_id=self.provider_id,
                recommendations=[],
                duration_ms=duration_ms,
                error=str(exc),
            )
