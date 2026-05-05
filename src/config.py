from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local vs cloud mode
    local_dev: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://platform:platform@localhost:5432/platform"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API Security
    api_key: str = "dev-key"

    # AWS
    aws_region: str = "eu-central-1"
    aws_account_id: str = ""

    # AWS IoT Core
    aws_iot_endpoint: str = ""
    aws_iot_policy_name: str = "HealthPlatformDevicePolicy"
    aws_iot_thing_type: str = "HealthPlatformDevice"

    # Kinesis
    kinesis_stream_name: str = "health-platform-events"
    kinesis_shard_count: int = 2

    # Recommendation providers
    service1_endpoint: str = (
        "https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service1"
    )
    service1_token: str = "service1-dev"
    service2_endpoint: str = (
        "https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service2"
    )
    service3_endpoint: str = ""
    service3_api_token: str = ""
    service3_schema: str = "service1_schema"

    # Aggregation
    recommendation_timeout_seconds: float = 0.8
    min_recommendation_score: float = 200.0

    # Staleness
    staleness_threshold_hours: int = 24

    # MQTT
    mqtt_broker_url: str = "mqtt://localhost:1883"
    mqtt_topic_prefix: str = "health/telemetry"

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "health-platform"

    # Logging
    log_level: str = "INFO"

    # Seeding
    seed_device_count: int = 10

    # Initial credits for new devices
    initial_credit_balance: int = 100

    # Delta Lake event archive
    delta_output_dir: str = "/data/delta"

    # Delta Lake recommendations archive
    recommendations_delta_dir: str = "/data/recommendations"

    # ML model artifacts
    model_artifact_dir: str = "/data/models"
    on_device_package_dir: str = "/data/packages"
    anomaly_threshold: float = 0.5
    embedding_ttl_seconds: int = 300
    min_telemetry_days: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
