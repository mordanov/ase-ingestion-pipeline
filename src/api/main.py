from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialised")
    return _http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting_up", local_dev=settings.local_dev)

    _http_client = httpx.AsyncClient(timeout=httpx.Timeout(1.5))

    import asyncio as _asyncio
    import os as _os

    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    _alembic_ini = _os.path.join(_os.path.dirname(__file__), "..", "..", "alembic.ini")
    _alembic_cfg = AlembicConfig(_alembic_ini)
    await _asyncio.to_thread(alembic_command.upgrade, _alembic_cfg, "head")
    logger.info("migrations_applied")

    from src.observability.tracing import configure_tracer

    configure_tracer(settings.otel_service_name)

    # Seed default credit config if missing
    from src.api.dependencies import get_db_session as _get_db
    from src.credits.config_service import ConfigService as _ConfigService

    async for _db in _get_db():
        await _ConfigService(_db).seed_default_if_missing()
        break

    # Seed Prometheus gauges from DB so dashboards show current state after restart
    from sqlalchemy import func as _func
    from sqlalchemy import select as _select

    from src.db.models import Device as _Device
    from src.observability.metrics import (
        ACTIVE_DEVICES_TOTAL as _ACTIVE_DEVICES_TOTAL,
    )
    from src.observability.metrics import (
        CREDIT_TIER_TOTAL as _CREDIT_TIER_TOTAL,
    )
    from src.observability.metrics import (
        DEVICE_CREDIT_BALANCE as _DEVICE_CREDIT_BALANCE,
    )
    from src.observability.metrics import (
        DEVICE_STREAK_DAYS as _DEVICE_STREAK_DAYS,
    )

    async for _db in _get_db():
        _count = (await _db.execute(_select(_func.count(_Device.id)))).scalar_one()
        _ACTIVE_DEVICES_TOTAL.set(_count)

        _devices = (await _db.execute(_select(_Device))).scalars().all()
        for _dev in _devices:
            _DEVICE_CREDIT_BALANCE.labels(device_id=_dev.device_id).set(_dev.credit_balance)
            _DEVICE_STREAK_DAYS.labels(device_id=_dev.device_id).set(_dev.streak_days or 0)

        _tier_rows = (
            await _db.execute(
                _select(_Device.reward_tier, _func.count(_Device.id)).group_by(_Device.reward_tier)
            )
        ).all()
        for _tier, _tier_count in _tier_rows:
            _CREDIT_TIER_TOTAL.labels(tier=_tier.value).set(_tier_count)
        break

    # Start MQTT consumer to ingest telemetry published to the local Mosquitto broker
    from urllib.parse import urlparse as _urlparse

    from src.api.dependencies import get_db_session as _get_db_mqtt
    from src.api.dependencies import get_publisher
    from src.ingestion.adapters.http_adapter import HttpIngestionAdapter
    from src.ingestion.adapters.mqtt_consumer import MqttConsumerConfig, MqttKinesisConsumer

    _mqtt_url = _urlparse(settings.mqtt_broker_url)
    _mqtt_consumer = MqttKinesisConsumer(
        config=MqttConsumerConfig(
            broker_host=_mqtt_url.hostname or "localhost",
            broker_port=_mqtt_url.port or 1883,
            topic=settings.mqtt_topic_prefix + "/+",
        ),
        adapter=HttpIngestionAdapter(),
        publisher=get_publisher(),
        session_factory=_get_db_mqtt,
    )
    import asyncio as _asyncio

    _asyncio.create_task(_mqtt_consumer.start())
    logger.info("mqtt_consumer_started", broker=settings.mqtt_broker_url)

    # Start background embedding refresh so per-device personalization is populated in Redis
    from src.api.dependencies import get_db_session as _get_db_embed
    from src.ml.feature_store import RedisFeatureStore, refresh_embeddings_for_all_devices

    _feature_store = RedisFeatureStore(
        redis_url=settings.redis_url,
        ttl_seconds=settings.embedding_ttl_seconds,
    )

    async def _start_embedding_refresh():
        async for _db in _get_db_embed():
            await refresh_embeddings_for_all_devices(
                feature_store=_feature_store,
                db=_db,
                telemetry_dir=settings.delta_output_dir,
                recommendations_dir=settings.recommendations_delta_dir,
                interval_seconds=settings.embedding_ttl_seconds // 2,
                min_telemetry_days=settings.min_telemetry_days,
            )
            break

    import asyncio as _asyncio

    _asyncio.create_task(_start_embedding_refresh())
    logger.info("embedding_refresh_task_started")

    # Import routers here to avoid circular imports at module load time
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

    yield

    await _http_client.aclose()
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
