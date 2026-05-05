from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawRecommendation:
    short_text: str
    normalised_score: float
    provider_id: str
    detail: str | None = None


@dataclass
class ProviderResult:
    provider_id: str
    recommendations: list[RawRecommendation]
    duration_ms: int
    error: str | None = None


class ProviderAdapter(ABC):
    provider_id: str

    @abstractmethod
    async def get_recommendations(self, height_cm: float, weight_kg: float) -> ProviderResult:
        """Fetch and normalise recommendations from an external provider."""
