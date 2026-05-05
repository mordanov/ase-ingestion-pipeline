import asyncio
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from src.api.dependencies import get_db_session, get_publisher
from src.api.http_client import close_http_client, init_http_client
from src.api.routers import (
    credit_config,
    devices,
    health,
    ingest,
    ml_metrics,
    ml_training,
    provider_schemas,
    recommendations,
    reports,
    rules,
)
from src.config import Settings, get_settings
from src.credits.config_service import ConfigService
from src.db.models import Device
from src.ingestion.adapters.http_adapter import HttpIngestionAdapter
from src.ingestion.adapters.mqtt_consumer import MqttConsumerConfig, MqttKinesisConsumer
from src.ml.feature_store import RedisFeatureStore, refresh_embeddings_for_all_devices
from src.observability.logging import configure_logging, get_logger
from src.observability.metrics import (
    ACTIVE_DEVICES_TOTAL,
    CREDIT_TIER_TOTAL,
    DEVICE_CREDIT_BALANCE,
    DEVICE_STREAK_DAYS,
)
from src.observability.tracing import configure_tracer

logger = get_logger(__name__)


async def _apply_migrations() -> None:
    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
    alembic_config = AlembicConfig(alembic_ini)
    await asyncio.to_thread(alembic_command.upgrade, alembic_config, "head")
    logger.info("migrations_applied")


async def _seed_default_credit_config() -> None:
    async for session in get_db_session():
        await ConfigService(session).seed_default_if_missing()
        break


async def _seed_prometheus_gauges() -> None:
    async for session in get_db_session():
        device_count = (await session.execute(select(func.count(Device.id)))).scalar_one()
        ACTIVE_DEVICES_TOTAL.set(device_count)

        devices_rows = (await session.execute(select(Device))).scalars().all()
        for device in devices_rows:
            DEVICE_CREDIT_BALANCE.labels(device_id=device.device_id).set(device.credit_balance)
            DEVICE_STREAK_DAYS.labels(device_id=device.device_id).set(device.streak_days or 0)

        tier_rows = (
            await session.execute(
                select(Device.reward_tier, func.count(Device.id)).group_by(Device.reward_tier)
            )
        ).all()
        for tier, tier_count in tier_rows:
            CREDIT_TIER_TOTAL.labels(tier=tier.value).set(tier_count)
        break


def _start_mqtt_consumer(settings: Settings) -> None:
    mqtt_url = urlparse(settings.mqtt_broker_url)
    consumer = MqttKinesisConsumer(
        config=MqttConsumerConfig(
            broker_host=mqtt_url.hostname or "localhost",
            broker_port=mqtt_url.port or 1883,
            topic=f"{settings.mqtt_topic_prefix}/+",
        ),
        adapter=HttpIngestionAdapter(),
        publisher=get_publisher(),
        session_factory=get_db_session,
    )
    asyncio.create_task(consumer.start())
    logger.info("mqtt_consumer_started", broker=settings.mqtt_broker_url)


def _start_embedding_refresh_task(settings: Settings) -> None:
    feature_store = RedisFeatureStore(
        redis_url=settings.redis_url,
        ttl_seconds=settings.embedding_ttl_seconds,
    )

    async def _run_refresh() -> None:
        async for session in get_db_session():
            await refresh_embeddings_for_all_devices(
                feature_store=feature_store,
                db=session,
                telemetry_dir=settings.delta_output_dir,
                recommendations_dir=settings.recommendations_delta_dir,
                interval_seconds=settings.embedding_ttl_seconds // 2,
                min_telemetry_days=settings.min_telemetry_days,
            )
            break

    asyncio.create_task(_run_refresh())
    logger.info("embedding_refresh_task_started")


def _register_routers(app: FastAPI) -> None:
    app.include_router(ingest.router)
    app.include_router(devices.router)
    app.include_router(recommendations.router)
    app.include_router(credit_config.router)
    app.include_router(provider_schemas.router)
    app.include_router(health.router)
    app.include_router(ml_training.router)
    app.include_router(ml_metrics.router)
    app.include_router(reports.router)
    app.include_router(rules.router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting_up", local_dev=settings.local_dev)

    init_http_client()
    await _apply_migrations()
    configure_tracer(settings.otel_service_name)
    await _seed_default_credit_config()
    await _seed_prometheus_gauges()
    _start_mqtt_consumer(settings)
    _start_embedding_refresh_task(settings)
    _register_routers(app)

    yield

    await close_http_client()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Health Intelligence Platform",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def api_key_middleware(request: Request, call_next):
        # Skip key check for health + metrics + docs
        open_paths = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}
        if request.url.path not in open_paths and not request.url.path.startswith("/ingest"):
            api_key = request.headers.get("X-API-Key")
            if api_key != settings.api_key:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        return await call_next(request)

    return application


app = create_app()
