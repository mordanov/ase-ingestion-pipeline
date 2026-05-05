import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.api.dependencies import DbSession
from src.db.models.provider_schema import ProviderSchema

router = APIRouter(prefix="/api/v1/provider-schemas", tags=["provider-schemas"])

# ── Pydantic models ───────────────────────────────────────────────────────────


class ResponseMapping(BaseModel):
    array_path: str = ""
    text_field: str = ""
    score_field: str = ""
    score_multiplier: float = 1.0
    detail_field: str = ""


class ProviderSchemaResponse(BaseModel):
    id: str
    name: str
    endpoint_url: str
    openapi_url: str | None
    request_mapping: dict
    response_mapping: dict
    is_active: bool
    created_at: str
    updated_at: str


class CreateProviderSchemaRequest(BaseModel):
    name: str
    endpoint_url: str
    openapi_url: str | None = None
    request_mapping: dict
    response_mapping: dict
    is_active: bool = True


class UpdateProviderSchemaRequest(BaseModel):
    name: str | None = None
    endpoint_url: str | None = None
    openapi_url: str | None = None
    request_mapping: dict | None = None
    response_mapping: dict | None = None
    is_active: bool | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


def _to_response(p: ProviderSchema) -> ProviderSchemaResponse:
    return ProviderSchemaResponse(
        id=str(p.id),
        name=p.name,
        endpoint_url=p.endpoint_url,
        openapi_url=p.openapi_url,
        request_mapping=p.request_mapping or {},
        response_mapping=p.response_mapping or {},
        is_active=p.is_active,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.get("", response_model=list[ProviderSchemaResponse])
async def list_provider_schemas(db: DbSession) -> Any:
    result = await db.execute(select(ProviderSchema).order_by(ProviderSchema.created_at))
    return [_to_response(p) for p in result.scalars().all()]


@router.post("", response_model=ProviderSchemaResponse, status_code=201)
async def create_provider_schema(body: CreateProviderSchemaRequest, db: DbSession) -> Any:
    existing = (
        await db.execute(select(ProviderSchema).where(ProviderSchema.name == body.name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider {body.name!r} already exists")

    now = datetime.now(UTC)
    p = ProviderSchema(
        id=uuid.uuid4(),
        name=body.name,
        endpoint_url=body.endpoint_url,
        openapi_url=body.openapi_url,
        openapi_schema=None,
        request_mapping=body.request_mapping,
        response_mapping=body.response_mapping,
        is_active=body.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _to_response(p)


@router.put("/{schema_id}", response_model=ProviderSchemaResponse)
async def update_provider_schema(
    schema_id: str, body: UpdateProviderSchemaRequest, db: DbSession
) -> Any:
    try:
        uid = uuid.UUID(schema_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid schema_id") from None

    p = (
        await db.execute(select(ProviderSchema).where(ProviderSchema.id == uid))
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Provider schema not found")

    if body.name is not None:
        p.name = body.name
    if body.endpoint_url is not None:
        p.endpoint_url = body.endpoint_url
    if body.openapi_url is not None:
        p.openapi_url = body.openapi_url
    if body.request_mapping is not None:
        p.request_mapping = body.request_mapping
    if body.response_mapping is not None:
        p.response_mapping = body.response_mapping
    if body.is_active is not None:
        p.is_active = body.is_active
    p.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(p)
    return _to_response(p)


@router.delete("/{schema_id}", status_code=204)
async def delete_provider_schema(schema_id: str, db: DbSession) -> None:
    try:
        uid = uuid.UUID(schema_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid schema_id") from None

    p = (
        await db.execute(select(ProviderSchema).where(ProviderSchema.id == uid))
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Provider schema not found")

    await db.delete(p)
    await db.commit()
