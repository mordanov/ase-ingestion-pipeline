import time

import httpx

from src.observability.logging import get_logger
from src.recommendation.interfaces import ProviderAdapter, ProviderResult, RawRecommendation

logger = get_logger(__name__)


class Service3Adapter(ProviderAdapter):
    """Service3 adapter — schema determined by SERVICE3_SCHEMA env var.

    Supports both service1_schema (confidence list) and service2_schema (priority dict).
    """

    provider_id = "service3"

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        endpoint: str,
        token: str,
        schema: str = "service1_schema",
    ):
        self._client = http_client
        self._endpoint = endpoint
        self._token = token
        self._schema = schema

    async def get_recommendations(self, height_cm: float, weight_kg: float) -> ProviderResult:
        start = time.monotonic()
        try:
            if self._schema == "service2_schema":
                return await self._call_service2_schema(height_cm, weight_kg, start)
            return await self._call_service1_schema(height_cm, weight_kg, start)
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("service3_error", error=str(exc))
            return ProviderResult(
                provider_id=self.provider_id,
                recommendations=[],
                duration_ms=duration_ms,
                error=str(exc),
            )

    async def _call_service1_schema(
        self, height_cm: float, weight_kg: float, start: float
    ) -> ProviderResult:
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
        if isinstance(body, dict) and "errorCode" in body:
            return ProviderResult(
                provider_id=self.provider_id,
                recommendations=[],
                duration_ms=duration_ms,
                error=body.get("errorMessage"),
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
        return ProviderResult(
            provider_id=self.provider_id, recommendations=recs, duration_ms=duration_ms
        )

    async def _call_service2_schema(
        self, height_cm: float, weight_kg: float, start: float
    ) -> ProviderResult:
        import uuid as _uuid

        mass_lbs = round(weight_kg * 2.20462, 4)
        height_feet = round(height_cm / 30.48, 4)
        resp = await self._client.post(
            self._endpoint,
            json={
                "measurements": {"mass": mass_lbs, "height": height_feet},
                "birth_date": 631152000,
                "session_token": str(_uuid.uuid4()),
            },
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
        if isinstance(body, dict) and "code" in body and "error" in body:
            return ProviderResult(
                provider_id=self.provider_id,
                recommendations=[],
                duration_ms=duration_ms,
                error=body["error"],
            )
        raw_recs = body.get("recommendations", [])
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
