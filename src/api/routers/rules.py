from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import DbSession
from src.db.models.device import Device
from src.db.models.disabled_device import DisabledDevice
from src.observability.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


class DisabledDeviceOut(BaseModel):
    device_id: str
    device_type: str
    disabled_at: str


class DisableDeviceRequest(BaseModel):
    device_id: str


@router.get("/disabled-devices", response_model=list[DisabledDeviceOut])
async def list_disabled_devices(db: DbSession) -> Any:
    rows = (
        await db.execute(
            select(DisabledDevice, Device.device_type)
            .join(Device, Device.device_id == DisabledDevice.device_id)
            .order_by(DisabledDevice.disabled_at.desc())
        )
    ).all()
    return [
        DisabledDeviceOut(
            device_id=dd.device_id,
            device_type=dev_type.value,
            disabled_at=dd.disabled_at.isoformat(),
        )
        for dd, dev_type in rows
    ]


@router.post("/disabled-devices", response_model=DisabledDeviceOut, status_code=201)
async def disable_device(body: DisableDeviceRequest, db: DbSession) -> Any:
    device = (
        await db.execute(select(Device).where(Device.device_id == body.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {body.device_id!r} is not registered")

    existing = (
        await db.execute(
            select(DisabledDevice).where(DisabledDevice.device_id == body.device_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Device {body.device_id!r} is already disabled")

    record = DisabledDevice(
        device_id=body.device_id,
        disabled_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()
    logger.info("device_disabled", device_id=body.device_id)
    return DisabledDeviceOut(
        device_id=record.device_id,
        device_type=device.device_type.value,
        disabled_at=record.disabled_at.isoformat(),
    )


@router.delete("/disabled-devices/{device_id}", status_code=204)
async def enable_device(device_id: str, db: DbSession) -> None:
    record = (
        await db.execute(
            select(DisabledDevice).where(DisabledDevice.device_id == device_id)
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Device {device_id!r} is not in the disabled list")
    await db.delete(record)
    logger.info("device_enabled", device_id=device_id)
