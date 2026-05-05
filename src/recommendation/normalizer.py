import re
from dataclasses import dataclass

from src.recommendation.interfaces import RawRecommendation


@dataclass
class AggregatedRecommendation:
    short_text: str
    max_score: float
    providers: list[str]
    detail: str | None = None


def normalize_score(
    provider_id: str, *, confidence: float | None = None, priority: int | None = None
) -> float:
    """Convert a provider-specific raw score to a normalised 0–1000 float."""
    if provider_id == "service1":
        if confidence is None:
            raise ValueError("confidence required for service1")
        return confidence * 1000.0
    if provider_id in ("service2", "service3"):
        if priority is None:
            raise ValueError("priority required for service2/3")
        return float(priority)
    raise ValueError(f"Unknown provider: {provider_id}")


def _normalise_key(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.strip().lower())


def group_and_sort(
    results: list[RawRecommendation],
    min_score: float = 0.0,
) -> list[AggregatedRecommendation]:
    """Group by normalised short_text, keep max score, sort descending."""
    groups: dict[str, dict] = {}

    for rec in results:
        key = _normalise_key(rec.short_text)
        if key not in groups:
            groups[key] = {
                "short_text": key,
                "max_score": rec.normalised_score,
                "best_detail": rec.detail,
                "providers": set(),
            }
        entry = groups[key]
        if rec.normalised_score > entry["max_score"]:
            entry["max_score"] = rec.normalised_score
            entry["best_detail"] = rec.detail
        entry["providers"].add(rec.provider_id)

    aggregated = [
        AggregatedRecommendation(
            short_text=v["short_text"],
            max_score=v["max_score"],
            providers=sorted(v["providers"]),
            detail=v["best_detail"],
        )
        for v in groups.values()
        if v["max_score"] >= min_score
    ]
    aggregated.sort(key=lambda r: r.max_score, reverse=True)
    return aggregated
