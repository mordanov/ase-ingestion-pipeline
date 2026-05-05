import asyncio
import time
from dataclasses import dataclass, field

from src.observability.logging import get_logger
from src.recommendation.interfaces import ProviderAdapter, ProviderResult, RawRecommendation
from src.recommendation.normalizer import AggregatedRecommendation, group_and_sort

logger = get_logger(__name__)


class AllProvidersFailedError(Exception):
    def __init__(self, providers: list[str], duration_ms: int):
        self.providers = providers
        self.duration_ms = duration_ms
        super().__init__(f"All providers failed: {providers}")


@dataclass
class AggregationResult:
    recommendations: list[AggregatedRecommendation]
    providers_called: list[str]
    providers_succeeded: list[str]
    duration_ms: int
    raw_results: list[ProviderResult] = field(default_factory=list)


async def aggregate(
    providers: list[ProviderAdapter],
    height_cm: float,
    weight_kg: float,
    timeout: float = 0.8,
    min_score: float = 0.0,
) -> AggregationResult:
    start = time.monotonic()
    providers_called = [p.provider_id for p in providers]

    async def _call(p: ProviderAdapter) -> ProviderResult:
        try:
            return await asyncio.wait_for(
                p.get_recommendations(height_cm, weight_kg),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("provider_timeout", provider=p.provider_id)
            return ProviderResult(
                provider_id=p.provider_id,
                recommendations=[],
                duration_ms=int(timeout * 1000),
                error="timeout",
            )
        except Exception as exc:
            logger.error("provider_error", provider=p.provider_id, error=str(exc))
            return ProviderResult(
                provider_id=p.provider_id, recommendations=[], duration_ms=0, error=str(exc)
            )

    results: list[ProviderResult] = await asyncio.gather(*[_call(p) for p in providers])

    providers_succeeded = [r.provider_id for r in results if r.error is None]
    all_recs: list[RawRecommendation] = [rec for r in results for rec in r.recommendations]

    duration_ms = int((time.monotonic() - start) * 1000)

    if not providers_succeeded:
        raise AllProvidersFailedError(providers_called, duration_ms)

    aggregated = group_and_sort(all_recs, min_score=min_score)
    return AggregationResult(
        recommendations=aggregated,
        providers_called=providers_called,
        providers_succeeded=providers_succeeded,
        duration_ms=duration_ms,
        raw_results=results,
    )
