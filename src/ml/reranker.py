import hashlib
import struct
import time as _time
from collections import deque
from typing import Optional

from opentelemetry import trace

from src.ml.interfaces import FeatureStore, ModelRegistry, Reranker
from src.observability.logging import get_logger
from src.observability.tracing import get_tracer

logger = get_logger(__name__)
_tracer = get_tracer("ml.reranker")

_LATENCY_WINDOW_SIZE = 1000


class TFLiteReranker(Reranker):
    def __init__(
        self,
        feature_store: FeatureStore,
        registry: ModelRegistry,
        min_telemetry_days: int = 7,
    ):
        self._feature_store = feature_store
        self._registry = registry
        self._min_telemetry_days = min_telemetry_days
        self._latency_window: deque = deque(maxlen=_LATENCY_WINDOW_SIZE)

    async def rerank(self, device_id: str, items: list, telemetry_days: int) -> list:
        """Re-rank items by personal relevance score.

        Returns list of (item, score | None) tuples sorted by score descending.
        Score is None when cold-start or ML is unavailable.
        """
        start = _time.monotonic()
        with _tracer.start_as_current_span("ml.reranker.rerank") as span:
            span.set_attribute("device_id", device_id)
            span.set_attribute("item_count", len(items))
            span.set_attribute("telemetry_days", telemetry_days)
            try:
                result = await self._do_rerank(device_id, items, telemetry_days)
                span.set_attribute("scored", any(s is not None for _, s in result))
            except Exception as exc:
                span.record_exception(exc)
                logger.warning("reranker_fallback", device_id=device_id, error=str(exc))
                result = [(item, None) for item in items]
            finally:
                elapsed_ms = (_time.monotonic() - start) * 1000
                self._latency_window.append(_time.monotonic() - start)
                logger.debug(
                    "reranker_inference",
                    device_id=device_id,
                    item_count=len(items),
                    telemetry_days=telemetry_days,
                    duration_ms=round(elapsed_ms, 2),
                )
        return result

    async def _do_rerank(self, device_id: str, items: list, telemetry_days: int) -> list:
        if not items:
            return []

        # Cold-start: fewer than minimum days of history → raw order, null scores
        if telemetry_days < self._min_telemetry_days:
            logger.debug("reranker_cold_start", device_id=device_id, telemetry_days=telemetry_days)
            return [(item, None) for item in items]

        # Retrieve cached user embedding
        embedding = await self._feature_store.get_embedding(device_id)
        if embedding is None:
            logger.info("reranker_embedding_cache_miss", device_id=device_id)
            # Return raw order; embedding will be recomputed asynchronously
            return [(item, None) for item in items]

        # Score each item using dot product between user vector and item features
        dim = len(embedding.vector) // 4
        user_vec = list(struct.unpack(f"{dim}f", embedding.vector))

        scored = []
        for item in items:
            item_vec = self._item_features(getattr(item, "short_text", str(item)), dim)
            raw_score = _dot(user_vec, item_vec)
            # Map to [0, 1] via sigmoid
            score = _sigmoid(raw_score)
            scored.append((item, round(score, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _item_features(self, text: str, dim: int) -> list[float]:
        """Deterministic item feature vector derived from text hash.

        In production this is replaced by the trained item-tower embeddings.
        """
        h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        return [((h >> (i * 8)) & 0xFF) / 255.0 - 0.5 for i in range(dim)]

    def get_p99_latency_ms(self) -> Optional[float]:
        if len(self._latency_window) < 10:
            return None
        sorted_latencies = sorted(self._latency_window)
        idx = max(0, int(len(sorted_latencies) * 0.99) - 1)
        return round(sorted_latencies[idx] * 1000, 2)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sigmoid(x: float) -> float:
    import math
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0
