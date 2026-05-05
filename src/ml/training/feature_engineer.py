import struct
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.ml.training.data_extractor import TelemetryRecord
from src.observability.logging import get_logger

logger = get_logger(__name__)

_EMBEDDING_DIM = 64
_MIN_DAYS = 1


@dataclass
class DeviceFeatures:
    device_id: str
    vector: bytes  # struct-packed float32 array of length EMBEDDING_DIM
    telemetry_days: int
    sample_count: int


class FeatureEngineer:
    """Transforms raw telemetry records into per-device feature vectors."""

    def __init__(self, min_days: int = _MIN_DAYS, embedding_dim: int = _EMBEDDING_DIM):
        self._min_days = min_days
        self._dim = embedding_dim

    def build_features(self, records: list[TelemetryRecord]) -> list[DeviceFeatures]:
        """Aggregate telemetry by device, compute feature vectors.

        Devices with fewer than min_days of data are excluded (FR-003, A-010).
        """
        groups: dict[str, list[TelemetryRecord]] = defaultdict(list)
        for r in records:
            if r.device_id:
                groups[r.device_id].append(r)

        features = []
        for device_id, device_records in groups.items():
            days = _count_days(device_records)
            if days < self._min_days:
                continue
            vec = self._compute_vector(device_records)
            features.append(DeviceFeatures(
                device_id=device_id,
                vector=vec,
                telemetry_days=days,
                sample_count=len(device_records),
            ))

        logger.info(
            "features_built",
            total_devices=len(groups),
            eligible_devices=len(features),
        )
        return features

    def _compute_vector(self, records: list[TelemetryRecord]) -> bytes:
        """Build a normalised feature vector from per-feature rolling statistics."""
        features: list[float] = []

        for getter in (
            lambda r: r.heart_rate,
            lambda r: r.steps,
            lambda r: r.sleep_duration,
        ):
            values = [v for r in records if (v := getter(r)) is not None]
            if values:
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                std = variance ** 0.5
                features.extend([mean / 200.0, std / 50.0])  # rough normalisation
            else:
                features.extend([0.0, 0.0])

        # Pad or truncate to target dimension
        if len(features) < self._dim:
            features.extend([0.0] * (self._dim - len(features)))
        features = features[: self._dim]

        return struct.pack(f"{self._dim}f", *features)


def _count_days(records: list[TelemetryRecord]) -> int:
    """Count the number of distinct calendar days covered by the records."""
    days: set[str] = set()
    for r in records:
        if r.event_timestamp:
            try:
                ts = r.event_timestamp[:10]  # YYYY-MM-DD
                days.add(ts)
            except Exception:
                pass
    return len(days)
