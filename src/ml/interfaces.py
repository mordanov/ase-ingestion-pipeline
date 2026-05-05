from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class UserEmbedding:
    device_id: str
    vector: bytes  # serialised float32 array (struct-packed)
    model_version: int
    computed_at: float  # Unix timestamp


@dataclass
class AnomalyResult:
    anomaly_score: float  # [0.0, 1.0]
    threshold_exceeded: bool
    has_baseline: bool  # False when user has < min_telemetry_days


class FeatureStore(ABC):
    @abstractmethod
    async def get_embedding(self, device_id: str) -> UserEmbedding | None: ...

    @abstractmethod
    async def set_embedding(self, device_id: str, vector: bytes, model_version: int) -> None: ...


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        device_id: str,
        items: list,
        telemetry_days: int,
    ) -> list:
        """Return items ordered by personal relevance.

        Each element is (item, score_or_None). Score is None on cold-start or ML unavailable.
        """
        ...

    def get_p99_latency_ms(self) -> float | None:
        return None


class AnomalyDetector(ABC):
    @abstractmethod
    async def detect(
        self,
        device_id: str,
        reading: dict,
        baseline_days: int,
    ) -> AnomalyResult: ...


class ModelRegistry(ABC):
    @abstractmethod
    async def get_active_artifact_path(self, model_type: str) -> str | None: ...

    @abstractmethod
    async def get_active_version(self, model_type: str) -> int | None: ...
