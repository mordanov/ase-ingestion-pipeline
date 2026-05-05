from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.db.base import get_db

# ── DB ────────────────────────────────────────────────────────────────────────


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


# ── HTTP client ───────────────────────────────────────────────────────────────


def get_http_client() -> httpx.AsyncClient:
    from src.api.main import get_http_client as _get

    return _get()


HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]


# ── Ingestion adapters (filled in Phase 3) ───────────────────────────────────


def get_publisher():
    from src.config import get_settings
    from src.ingestion.publisher import KinesisPublisher, LocalRedisStreamsPublisher

    settings = get_settings()
    if settings.local_dev:
        return LocalRedisStreamsPublisher(settings.redis_url, settings.kinesis_stream_name)
    return KinesisPublisher(settings.kinesis_stream_name, settings.aws_region)


Publisher = Annotated[object, Depends(get_publisher)]


# ── Recommendation providers (filled in Phase 3) ─────────────────────────────


async def get_provider_adapters(http_client: HttpClient, settings: AppSettings, db: DbSession):
    from sqlalchemy import select as _select

    from src.db.models.provider_schema import ProviderSchema
    from src.recommendation.adapters.dynamic_adapter import DynamicAdapter
    from src.recommendation.adapters.service1_adapter import Service1Adapter
    from src.recommendation.adapters.service2_adapter import Service2Adapter

    adapters = [
        Service1Adapter(http_client, settings.service1_endpoint, settings.service1_token),
        Service2Adapter(http_client, settings.service2_endpoint),
    ]
    if settings.service3_endpoint:
        from src.recommendation.adapters.service3_adapter import Service3Adapter

        adapters.append(
            Service3Adapter(
                http_client,
                settings.service3_endpoint,
                settings.service3_api_token,
                settings.service3_schema,
            )
        )

    rows = (
        (await db.execute(_select(ProviderSchema).where(ProviderSchema.is_active))).scalars().all()
    )
    for row in rows:
        adapters.append(
            DynamicAdapter(
                http_client,
                row.name,
                row.endpoint_url,
                row.request_mapping or {},
                row.response_mapping or {},
            )
        )

    return adapters


ProviderAdapters = Annotated[list, Depends(get_provider_adapters)]


# ── Twin registry (filled in Phase 4) ────────────────────────────────────────


def get_twin_adapter(settings: AppSettings):
    if settings.local_dev:
        from src.digital_twin.local_registry_adapter import LocalRegistryAdapter

        return LocalRegistryAdapter()
    from src.digital_twin.iot_core_adapter import IotCoreAdapter

    return IotCoreAdapter(
        settings.aws_region,
        settings.aws_iot_endpoint,
        settings.aws_iot_policy_name,
        settings.aws_iot_thing_type,
    )


TwinAdapter = Annotated[object, Depends(get_twin_adapter)]


# ── Credits (filled in Phase 5) ──────────────────────────────────────────────


@lru_cache
def get_credit_ledger():
    from src.credits.ledger import CreditLedger

    return CreditLedger()


CreditLedgerDep = Annotated[object, Depends(get_credit_ledger)]


@lru_cache
def get_tier_engine():
    from src.credits.tier_engine import TierEngine

    return TierEngine()


TierEngineDep = Annotated[object, Depends(get_tier_engine)]
