import time
import uuid as _uuid_mod
from typing import Any

import httpx

from src.observability.logging import get_logger
from src.recommendation.interfaces import ProviderAdapter, ProviderResult, RawRecommendation
from src.recommendation.retry import post_with_retry

logger = get_logger(__name__)


def _set_nested(d: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def _get_nested(d: Any, path: str) -> Any:
    if not path:
        return d
    for part in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _resolve_expr(expr: str, height_cm: float, weight_kg: float) -> Any:
    """Resolve a $EXPR string into a concrete value.

    Supported expressions:
      $HEIGHT      — patient height in cm
      $HEIGHT_FT   — patient height converted to feet
      $WEIGHT      — patient weight in kg
      $WEIGHT_LBS  — patient weight converted to lbs
      $UUID        — random UUID generated per request
      $CONST:value — literal value (parsed as int/float if possible)
    """
    if expr == "$HEIGHT":
        return height_cm
    if expr == "$HEIGHT_FT":
        return round(height_cm / 30.48, 4)
    if expr == "$WEIGHT":
        return weight_kg
    if expr == "$WEIGHT_LBS":
        return round(weight_kg * 2.20462, 4)
    if expr == "$UUID":
        return str(_uuid_mod.uuid4())
    if expr == "$BIRTHDATE":
        import time as _time

        return int(_time.time())
    if expr.startswith("$CONST:"):
        raw = expr[7:]
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw
    return None


def _resolve_legacy(cfg: dict, height_cm: float, weight_kg: float) -> Any:
    """Handle the old {source, transform, value} mapping format."""
    source = cfg.get("source", "static")
    transform = cfg.get("transform")

    if source == "height_cm":
        value: Any = height_cm
        if transform == "cm_to_feet":
            value = round(height_cm / 30.48, 4)
    elif source == "weight_kg":
        value = weight_kg
        if transform == "kg_to_lbs":
            value = round(weight_kg * 2.20462, 4)
    elif source == "uuid":
        value = str(_uuid_mod.uuid4())
    elif source == "timestamp":
        value = cfg.get("value", 631152000)
    else:
        value = cfg.get("value")
    return value


class DynamicAdapter(ProviderAdapter):
    """Generic adapter driven by request_mapping + response_mapping stored in the DB.

    request_mapping.fields maps each dot-notation field path to a value expression:
      "$HEIGHT"        — patient height in cm
      "$HEIGHT_FT"     — patient height in feet
      "$WEIGHT"        — patient weight in kg
      "$WEIGHT_LBS"    — patient weight in lbs
      "$UUID"          — random UUID per request
      "$CONST:value"   — literal value (e.g. "$CONST:service1-dev", "$CONST:42")

    Legacy {source, transform, value} dict format is also accepted for existing rows.

    response_mapping controls how recommendations are extracted from the response:
      array_path:       "" = root is the array; "recommendations" = body["recommendations"]
      text_field:       field name containing the recommendation text
      score_field:      field name containing the numeric score
      score_multiplier: multiplier applied to the raw score
      detail_field:     optional field for extended detail text
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        provider_id: str,
        endpoint_url: str,
        request_mapping: dict,
        response_mapping: dict,
    ):
        self.provider_id = provider_id
        self._client = http_client
        self._endpoint = endpoint_url
        self._request_mapping = request_mapping
        self._response_mapping = response_mapping

    def _build_request(self, height_cm: float, weight_kg: float) -> dict:
        body: dict = {}
        for field_path, expr in self._request_mapping.get("fields", {}).items():
            if isinstance(expr, str):
                value = _resolve_expr(expr, height_cm, weight_kg)
            elif isinstance(expr, dict):
                value = _resolve_legacy(expr, height_cm, weight_kg)
            else:
                value = None
            if value is not None:
                _set_nested(body, field_path, value)
        return body

    def _parse_response(self, body: Any) -> list[RawRecommendation]:
        rm = self._response_mapping
        array_path = rm.get("array_path", "")
        items = _get_nested(body, array_path) if array_path else body
        if not isinstance(items, list):
            items = []

        text_field = rm.get("text_field", "")
        score_field = rm.get("score_field", "")
        score_multiplier = float(rm.get("score_multiplier", 1))
        detail_field = rm.get("detail_field", "") or None

        if not text_field or not score_field:
            return []

        return [
            RawRecommendation(
                short_text=item[text_field],
                detail=item.get(detail_field) if detail_field else None,
                normalised_score=float(item[score_field]) * score_multiplier,
                provider_id=self.provider_id,
            )
            for item in items
            if text_field in item and score_field in item
        ]

    async def get_recommendations(self, height_cm: float, weight_kg: float) -> ProviderResult:
        start = time.monotonic()
        try:
            req_body = self._build_request(height_cm, weight_kg)
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

            resp_body = resp.json()
            if isinstance(resp_body, dict) and "body" in resp_body and "statusCode" in resp_body:
                import json as _json

                raw = resp_body["body"]
                resp_body = _json.loads(raw) if isinstance(raw, str) else raw

            recs = self._parse_response(resp_body)
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
