"""Device registration and twin state endpoints (fully implemented in US2 / T037-T045)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from src.api.dependencies import DbSession, TwinAdapter
from src.credits.config_service import ConfigService
from src.credits.ledger import CreditLedger
from src.credits.tier_engine import TierEngine
from src.db.models import Device, DeviceType, RewardTier
from src.db.models.credits import CreditActionType, CreditTransaction
from src.db.models.telemetry import TelemetryEvent
from src.observability.logging import get_logger
from src.observability.metrics import ACTIVE_DEVICES_TOTAL

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["devices"])


class RegisterDeviceRequest(BaseModel):
    device_id: str
    device_type: str
    model: str
    firmware_version: str
    os: str
    user_id: str
    height_cm: float
    weight_kg: float


class DeviceResponse(BaseModel):
    device_id: str
    device_type: str
    model: str
    firmware_version: str
    os: str
    credit_balance: int
    reward_tier: str
    registered_at: str
    iot_thing_name: str | None = None


class TopUpRequest(BaseModel):
    amount: int
    reason: str = "manual top-up"


class TopUpResponse(BaseModel):
    device_id: str
    credit_balance: int
    reward_tier: str


class DeviceCreditDetail(BaseModel):
    device_id: str
    credit_balance: int
    reward_tier: str
    streak_days: int
    cumulative_credits_earned: int
    cumulative_credits_spent: int
    next_tier: str | None
    credits_to_next_tier: int | None
    tier_multiplier: float
    tier_discount: float


class TransactionItem(BaseModel):
    id: str
    amount: int
    action_type: str
    reason: str
    resulting_balance: int
    created_at: str
    event_id: str | None = None


class TransactionHistoryResponse(BaseModel):
    total: int
    items: list[TransactionItem]


class MeasurementItem(BaseModel):
    event_id: str
    event_timestamp: str
    received_at: str
    scenario: str | None
    heart_rate_bpm: int | None
    spo2_pct: float | None
    validation_status: str
    is_anomaly: bool
    source_protocol: str


class MeasurementHistoryResponse(BaseModel):
    total: int
    items: list[MeasurementItem]


class DeviceListItem(BaseModel):
    device_id: str
    credit_balance: int
    reward_tier: str
    streak_days: int
    cumulative_credits_earned: int
    cumulative_credits_spent: int


class DeviceListResponse(BaseModel):
    total: int
    items: list[DeviceListItem]


def _device_or_404(device: Device | None, device_id: str) -> Device:
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {device_id!r} not found")
    return device


def _to_device_response(device: Device) -> DeviceResponse:
    return DeviceResponse(
        device_id=device.device_id,
        device_type=device.device_type.value,
        model=device.model,
        firmware_version=device.firmware_version,
        os=device.os,
        credit_balance=device.credit_balance,
        reward_tier=device.reward_tier.value,
        registered_at=device.registered_at.isoformat(),
        iot_thing_name=device.iot_thing_name,
    )


def _to_device_list_item(device: Device) -> DeviceListItem:
    return DeviceListItem(
        device_id=device.device_id,
        credit_balance=device.credit_balance,
        reward_tier=device.reward_tier.value,
        streak_days=device.streak_days or 0,
        cumulative_credits_earned=device.cumulative_credits_earned or 0,
        cumulative_credits_spent=device.cumulative_credits_spent or 0,
    )


def _to_transaction_item(transaction: CreditTransaction) -> TransactionItem:
    return TransactionItem(
        id=str(transaction.id),
        amount=transaction.amount,
        action_type=transaction.action_type.value,
        reason=transaction.reason,
        resulting_balance=transaction.resulting_balance,
        created_at=transaction.created_at.isoformat(),
        event_id=transaction.event_id,
    )


def _to_measurement_item(event: TelemetryEvent) -> MeasurementItem:
    payload = event.payload or {}
    heart_rate = payload.get("heart_rate") or {}
    spo2 = payload.get("spo2") or {}
    return MeasurementItem(
        event_id=event.event_id,
        event_timestamp=event.event_timestamp.isoformat(),
        received_at=event.received_at.isoformat(),
        scenario=payload.get("scenario"),
        heart_rate_bpm=heart_rate.get("bpm"),
        spo2_pct=spo2.get("percentage"),
        validation_status=event.validation_status.value,
        is_anomaly=event.is_anomaly,
        source_protocol=event.source_protocol.value,
    )


async def _fetch_device(db: DbSession, device_id: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    return result.scalar_one_or_none()


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    db: DbSession,
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> Any:
    base_query = select(Device)
    if search:
        base_query = base_query.where(Device.device_id.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    items_result = await db.execute(
        base_query.order_by(Device.credit_balance.desc()).limit(limit).offset(offset)
    )
    devices = items_result.scalars().all()

    return DeviceListResponse(
        total=total,
        items=[
            DeviceListItem(
                device_id=d.device_id,
                credit_balance=d.credit_balance,
                reward_tier=d.reward_tier.value,
                streak_days=d.streak_days or 0,
                cumulative_credits_earned=d.cumulative_credits_earned or 0,
                cumulative_credits_spent=d.cumulative_credits_spent or 0,
            )
            for d in devices
        ],
    )


@router.post("/devices", response_model=DeviceResponse, status_code=201)
async def register_device(
    body: RegisterDeviceRequest,
    db: DbSession,
    twin_adapter: TwinAdapter,
) -> Any:
    config_svc = ConfigService(db)

    existing = await _fetch_device(db, body.device_id)

    if existing:
        return _to_device_response(existing)

    iot_thing_name: str | None = None
    try:
        iot_thing_name = await twin_adapter.register(body.device_id, body.device_type)
    except Exception as exc:
        logger.warning("twin_registration_failed", device_id=body.device_id, error=str(exc))

    credit_config = await config_svc.get_active()
    initial_balance = credit_config.default_initial_balance

    device = Device(
        id=uuid.uuid4(),
        device_id=body.device_id,
        device_type=DeviceType(body.device_type),
        model=body.model,
        firmware_version=body.firmware_version,
        os=body.os,
        user_id=body.user_id,
        height_cm=body.height_cm,
        weight_kg=body.weight_kg,
        credit_balance=initial_balance,
        cumulative_credits_spent=0,
        reward_tier=RewardTier.bronze,
        iot_thing_name=iot_thing_name,
        registered_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    ACTIVE_DEVICES_TOTAL.inc()

    logger.info("device_registered", device_id=device.device_id)
    return _to_device_response(device)


@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: str, db: DbSession) -> Any:
    device = _device_or_404(await _fetch_device(db, device_id), device_id)
    return _to_device_response(device)


@router.get("/devices/{device_id}/credits", response_model=DeviceCreditDetail)
async def get_device_credits(device_id: str, db: DbSession) -> Any:
    device = _device_or_404(await _fetch_device(db, device_id), device_id)

    config = await ConfigService(db).get_active()
    tier_engine = TierEngine()

    thresholds = config.tier_thresholds  # {"silver": ..., "gold": ..., "platinum": ...}
    tier_order = ["bronze", "silver", "gold", "platinum"]
    current_idx = tier_order.index(device.reward_tier.value)
    earned = device.cumulative_credits_earned or 0

    if current_idx < len(tier_order) - 1:
        next_tier = tier_order[current_idx + 1]
        next_threshold = thresholds.get(next_tier, 0)
        credits_to_next = max(0, next_threshold - earned)
    else:
        next_tier = None
        credits_to_next = None

    multiplier = tier_engine.get_multiplier(device.reward_tier, config)
    discount = float(config.tier_discounts.get(device.reward_tier.value, 0.0))

    return DeviceCreditDetail(
        device_id=device.device_id,
        credit_balance=device.credit_balance,
        reward_tier=device.reward_tier.value,
        streak_days=device.streak_days or 0,
        cumulative_credits_earned=earned,
        cumulative_credits_spent=device.cumulative_credits_spent or 0,
        next_tier=next_tier,
        credits_to_next_tier=credits_to_next,
        tier_multiplier=multiplier,
        tier_discount=discount,
    )


@router.get("/devices/{device_id}/credits/transactions", response_model=TransactionHistoryResponse)
async def get_device_transactions(
    device_id: str,
    db: DbSession,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    action_type: str | None = Query(default=None),
) -> Any:
    _device_or_404(await _fetch_device(db, device_id), device_id)

    base_query = select(CreditTransaction).where(CreditTransaction.device_id == device_id)
    if action_type is not None:
        try:
            base_query = base_query.where(
                CreditTransaction.action_type == CreditActionType(action_type)
            )
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"Unknown action_type: {action_type!r}"
            ) from None

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    items_result = await db.execute(
        base_query.order_by(CreditTransaction.created_at.desc()).limit(limit).offset(offset)
    )
    items = items_result.scalars().all()

    return TransactionHistoryResponse(
        total=total,
        items=[_to_transaction_item(transaction) for transaction in items],
    )


@router.get("/devices/{device_id}/events", response_model=MeasurementHistoryResponse)
async def get_device_events(
    device_id: str,
    db: DbSession,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> Any:
    _device_or_404(await _fetch_device(db, device_id), device_id)

    base_query = select(TelemetryEvent).where(TelemetryEvent.device_id == device_id)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    items_result = await db.execute(
        base_query.order_by(TelemetryEvent.event_timestamp.desc()).limit(limit).offset(offset)
    )
    events = items_result.scalars().all()

    return MeasurementHistoryResponse(
        total=total,
        items=[_to_measurement_item(event) for event in events],
    )


@router.post("/devices/{device_id}/credits", response_model=TopUpResponse)
async def top_up_credits(device_id: str, body: TopUpRequest, db: DbSession) -> Any:
    device = _device_or_404(await _fetch_device(db, device_id), device_id)

    if body.amount == 0:
        raise HTTPException(status_code=400, detail="amount must be non-zero")

    config = await ConfigService(db).get_active()
    ledger = CreditLedger()
    action_type = CreditActionType.top_up if body.amount > 0 else CreditActionType.adjustment
    await ledger.update_device_balance(
        session=db,
        device=device,
        delta=body.amount,
        action_type=action_type,
        reason=body.reason,
        config=config,
    )
    await db.commit()
    await db.refresh(device)

    return TopUpResponse(
        device_id=device.device_id,
        credit_balance=device.credit_balance,
        reward_tier=device.reward_tier.value,
    )
