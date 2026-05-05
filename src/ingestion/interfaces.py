from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class SourceProtocol(str, Enum):
    HTTP = "http"
    MQTT = "mqtt"


@dataclass
class IngestionEvent:
    device_id: str
    event_id: str
    source_protocol: SourceProtocol
    event_timestamp: datetime
    payload: dict[str, Any]
    trace_id: str
    is_batch: bool = False
    batch_id: str | None = None
    is_anomaly: bool = False


class IngestionAdapter(ABC):
    @abstractmethod
    async def parse(self, raw: dict[str, Any]) -> list[IngestionEvent]:
        """Parse raw request body into one or more IngestionEvents."""


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: IngestionEvent) -> None:
        """Publish a validated event to the stream."""
