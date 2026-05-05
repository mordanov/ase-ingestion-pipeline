from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import aiomqtt

from src.ingestion.interfaces import (
    EventPublisher,
    IngestionAdapter,
    SourceProtocol,
)
from src.ingestion.validator import quarantine_event, validate_event
from src.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MqttConsumerConfig:
    broker_host: str = "localhost"
    broker_port: int = 1883
    topic: str = "health/telemetry/+"
    keepalive: int = 60
    reconnect_interval: float = 5.0


class MqttKinesisConsumer:
    """Subscribes to MQTT telemetry topic and forwards events to the event publisher."""

    def __init__(
        self,
        config: MqttConsumerConfig,
        adapter: IngestionAdapter,
        publisher: EventPublisher,
        session_factory,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._publisher = publisher
        self._session_factory = session_factory
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._run_session()
            except aiomqtt.MqttError as exc:
                if not self._running:
                    break
                logger.warning(
                    "mqtt_disconnected", error=str(exc), retry_in=self._config.reconnect_interval
                )
                await asyncio.sleep(self._config.reconnect_interval)
            except Exception as exc:
                logger.error("mqtt_consumer_error", error=str(exc))
                if not self._running:
                    break
                await asyncio.sleep(self._config.reconnect_interval)

    async def stop(self) -> None:
        self._running = False

    async def _run_session(self) -> None:
        async with aiomqtt.Client(
            hostname=self._config.broker_host,
            port=self._config.broker_port,
            keepalive=self._config.keepalive,
        ) as client:
            await client.subscribe(self._config.topic)
            logger.info("mqtt_subscribed", topic=self._config.topic)
            async for message in client.messages:
                if not self._running:
                    break
                await self._handle_message(message)

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        try:
            raw = json.loads(message.payload)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("mqtt_invalid_json", topic=str(message.topic), error=str(exc))
            return

        try:
            events = await self._adapter.parse(raw)
        except Exception as exc:
            logger.warning("mqtt_parse_error", error=str(exc))
            return

        async for session in self._session_factory():
            for event in events:
                event.source_protocol = SourceProtocol.MQTT
                result = await validate_event(event, session)
                if not result.is_valid:
                    await quarantine_event(
                        event, result.error_code or "INVALID", result.error_message or "", session
                    )
                    continue
                if result.is_anomaly:
                    event.is_anomaly = True
                try:
                    await self._publisher.publish(event)
                except Exception as exc:
                    logger.error("mqtt_publish_error", event_id=event.event_id, error=str(exc))
            break
