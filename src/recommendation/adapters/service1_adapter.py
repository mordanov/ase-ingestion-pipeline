import time

import httpx

from src.observability.logging import get_logger
from src.recommendation.interfaces import ProviderAdapter, ProviderResult, RawRecommendation

logger = get_logger(__name__)


class Service1Adapter(ProviderAdapter):
    provider_id = "service1"

    def __init__(self, http_client: httpx.AsyncClient, endpoint: str, token: str):
        self._client = http_client
        self._endpoint = endpoint
        self._token = token

    async def get_recommendations(self, height_cm: float, weight_kg: float) -> ProviderResult:
        start = time.monotonic()
        try:
            resp = await self._client.post(
                self._endpoint,
                json={"height": height_cm, "weight": weight_kg, "token": self._token},
            )
            duration_ms = int((time.monotonic() - start) * 1000)

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

            if isinstance(body, dict) and "errorCode" in body:
                return ProviderResult(
                    provider_id=self.provider_id,
                    recommendations=[],
                    duration_ms=duration_ms,
                    error=body.get("errorMessage", "Service1 error"),
                )

            recs = [
                RawRecommendation(
                    short_text=item["recommendation"],
                    detail=None,
                    normalised_score=item["confidence"] * 1000,
                    provider_id=self.provider_id,
                )
                for item in body
                if "recommendation" in item and "confidence" in item
            ]
            return ProviderResult(provider_id=self.provider_id, recommendations=recs, duration_ms=duration_ms)

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("service1_error", error=str(exc))
            return ProviderResult(provider_id=self.provider_id, recommendations=[], duration_ms=duration_ms, error=str(exc))
