import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import DbSession, Publisher
from src.config import get_settings
from src.db.models import TelemetryEvent
from src.db.models.telemetry import SourceProtocol as DBSourceProtocol, ValidationStatus
from src.ingestion.adapters.http_adapter import HttpIngestionAdapter, ValidationError as ParseError
from src.ingestion.delta_writer import DeltaEventWriter, EventRecord
from src.ingestion.validator import ValidationError, quarantine_event, validate_event
from src.observability.logging import bind_trace_id, get_logger
from src.observability.metrics import INGEST_EVENTS_TOTAL, INGEST_QUARANTINE_TOTAL

logger = get_logger(__name__)
router = APIRouter(tags=["ingest"])

_adapter = HttpIngestionAdapter()
_delta_writer = DeltaEventWriter(get_settings().delta_output_dir)


class EventCreditResult(BaseModel):
    device_id: str
    activity_reward: int
    resulting_balance: int
    reward_tier: str


class IngestResponse(BaseModel):
    trace_id: str
    accepted: int
    quarantined: int
    batch_id: str | None = None
    credit_results: list[EventCreditResult] = []
    device_disabled_ids: list[str] = []


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest(
    request: Request,
    db: DbSession,
    publisher: Publisher,
) -> Any:
    trace_id = str(uuid.uuid4().hex)
    bind_trace_id(trace_id)

    raw = await request.json()
    batch_id: str | None = raw.get("batch_id") if "events" in raw else None

    try:
        events = await _adapter.parse(raw)
    except ParseError:
        return IngestResponse(
            trace_id=trace_id,
            accepted=0,
            quarantined=1,
            batch_id=batch_id,
        )

    accepted = 0
    quarantined = 0
    credit_results: list[EventCreditResult] = []
    accepted_records: list[EventRecord] = []
    device_disabled_ids: list[str] = []

    from src.credits.config_service import ConfigService
    from src.credits.earning_service import EarningService
    from src.db.models import Device

    config_svc = ConfigService(db)
    earning_svc = EarningService(db, config_svc)

    for event in events:
        event.trace_id = trace_id
        try:
            result = await validate_event(event, db)
            if not result.is_valid:
                await quarantine_event(event, result.error_code or "INVALID", result.error_message or "", db)
                quarantined += 1
                if result.error_code == "DEVICE_DISABLED":
                    device_disabled_ids.append(event.device_id)
                continue

            event.is_anomaly = result.is_anomaly

            dup = await db.execute(select(TelemetryEvent.id).where(TelemetryEvent.event_id == event.event_id))
            if dup.scalar_one_or_none() is not None:
                continue  # idempotent: duplicate event_id silently skipped

            validation_status = ValidationStatus.stale if result.is_stale else ValidationStatus.valid
            te = TelemetryEvent(
                id=uuid.uuid4(),
                event_id=event.event_id,
                device_id=event.device_id,
                source_protocol=DBSourceProtocol.http,
                event_timestamp=event.event_timestamp,
                is_stale=result.is_stale,
                is_anomaly=result.is_anomaly,
                validation_status=validation_status,
                payload=event.payload,
                trace_id=trace_id,
            )
            db.add(te)

            # Award credits for this event
            device_result = await db.execute(select(Device).where(Device.device_id == event.device_id))
            device = device_result.scalar_one_or_none()
            if device is not None:
                try:
                    awarded = await earning_svc.award_for_event(event, device)
                    tier = device.reward_tier
                    credit_results.append(EventCreditResult(
                        device_id=event.device_id,
                        activity_reward=awarded,
                        resulting_balance=device.credit_balance,
                        reward_tier=tier.value if hasattr(tier, "value") else str(tier),
                    ))
                except Exception as earn_exc:
                    logger.warning("earning_failed", event_id=event.event_id, error=str(earn_exc))

            try:
                await publisher.publish(event)
            except Exception as pub_exc:
                logger.warning("publish_failed", event_id=event.event_id, error=str(pub_exc))

            accepted_records.append(EventRecord(event=event, is_stale=result.is_stale))
            accepted += 1

        except ValidationError as exc:
            await quarantine_event(event, exc.code, exc.message, db)
            quarantined += 1

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Duplicate event_id — silently skip (idempotent ingest)

    if accepted_records:
        try:
            await _delta_writer.write(accepted_records)
        except Exception as exc:
            logger.warning("delta_write_failed", error=str(exc))

    INGEST_EVENTS_TOTAL.labels(protocol="http", status="accepted").inc(accepted)
    if quarantined:
        INGEST_EVENTS_TOTAL.labels(protocol="http", status="quarantined").inc(quarantined)
        INGEST_QUARANTINE_TOTAL.inc(quarantined)

    logger.info("ingest_complete", trace_id=trace_id, accepted=accepted, quarantined=quarantined)
    return IngestResponse(
        trace_id=trace_id,
        accepted=accepted,
        quarantined=quarantined,
        batch_id=batch_id,
        credit_results=credit_results,
        device_disabled_ids=device_disabled_ids,
    )
