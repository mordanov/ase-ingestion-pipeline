"""Shared pytest fixtures for all test suites."""
import os
import uuid

# Set test API key before any app module is imported so get_settings() picks it up.
# Must happen before first import of src.config to avoid lru_cache serving stale value.
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("LOCAL_DEV", "true")
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.db.models import Device, DeviceType, RewardTier

# Integration tests require a live PostgreSQL database.
# Set TEST_DATABASE_URL to override (e.g., in CI or docker-compose).
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://platform:platform@localhost:5432/platform_test",
)


# ── Database ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def engine():
    from src.db.base import Base
    eng = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ── App / HTTP client ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from contextlib import asynccontextmanager

    import httpx
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    from src.api.dependencies import get_db_session, get_provider_adapters, get_publisher
    from src.api.routers import credit_config, devices, health, ingest, recommendations
    from src.api.routers import ml_training, ml_metrics
    from src.config import get_settings
    from src.credits.config_service import ConfigService
    from src.observability.logging import configure_logging
    from src.recommendation.adapters.service1_adapter import Service1Adapter
    from src.recommendation.adapters.service2_adapter import Service2Adapter

    settings = get_settings()

    @asynccontextmanager
    async def _test_lifespan(application):
        from src.api import main as _main
        configure_logging(settings.log_level)
        _main._http_client = httpx.AsyncClient(timeout=httpx.Timeout(1.5))
        await ConfigService(db_session).seed_default_if_missing()
        yield
        await _main._http_client.aclose()

    app = FastAPI(title="Test App", lifespan=_test_lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        open_paths = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}
        if request.url.path not in open_paths and not request.url.path.startswith("/ingest"):
            if request.headers.get("X-API-Key") != settings.api_key:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        return await call_next(request)

    # Include routers at creation time — Starlette 1.x freezes routes at startup
    app.include_router(ingest.router)
    app.include_router(devices.router)
    app.include_router(recommendations.router)
    app.include_router(credit_config.router)
    app.include_router(health.router)
    app.include_router(ml_training.router)
    app.include_router(ml_metrics.router)

    async def _override_db():
        yield db_session

    mock_publisher = AsyncMock()
    mock_publisher.publish = AsyncMock()

    # Provide real adapter instances with dummy endpoints so patch() calls work
    _s1 = Service1Adapter(httpx.AsyncClient(), "http://mock-service1", "mock-token")
    _s2 = Service2Adapter(httpx.AsyncClient(), "http://mock-service2")

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_publisher] = lambda: mock_publisher
    app.dependency_overrides[get_provider_adapters] = lambda: [_s1, _s2]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── Mock provider responders ───────────────────────────────────────────────────

@pytest.fixture
def mock_service1():
    def _responder(height: float, weight: float, token: str) -> list[dict]:
        return [
            {"confidence": 0.8, "recommendation": "Walk more"},
            {"confidence": 0.5, "recommendation": "Drink water"},
        ]
    return _responder


@pytest.fixture
def mock_service2():
    def _responder(measurements: dict, birth_date: int, session_token: str) -> dict:
        return {
            "recommendations": [
                {"priority": 800, "title": "Walk more", "details": "Daily walking improves fitness."},
                {"priority": 600, "title": "Sleep 8 hours", "details": None},
            ]
        }
    return _responder


# ── Seeded device ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def seeded_device(db_session: AsyncSession) -> Device:
    device = Device(
        id=uuid.uuid4(),
        device_id=f"smartwatch-test-{uuid.uuid4().hex[:8]}",
        device_type=DeviceType.smartwatch,
        model="TestWatch Pro",
        firmware_version="2.2.3",
        os="WatchOS 10",
        user_id="test-user-001",
        height_cm=175.0,
        weight_kg=70.0,
        credit_balance=100,
        cumulative_credits_spent=0,
        reward_tier=RewardTier.bronze,
        registered_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


# ── Telemetry event factory ────────────────────────────────────────────────────

def make_telemetry_event(device_id: str = "", **overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "device_id": device_id,
        "device_type": "smartwatch",
        "user_id": "test-user-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": "rest",
        "is_anomaly": False,
        "protocol": "http",
        "firmware_version": "2.2.3",
        "heart_rate": {"bpm": 72, "hrv_ms": 55.0},
        "spo2": {"percentage": 98.0},
    }
    base.update(overrides)
    return base
