import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class DeviceType(enum.StrEnum):
    smartwatch = "smartwatch"
    fitness_tracker = "fitness_tracker"
    smartphone = "smartphone"
    laptop = "laptop"


class RewardTier(enum.StrEnum):
    bronze = "bronze"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Use device_id as a separate unique business key matching simulator's device_id / cert CN
    device_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    firmware_version: Mapped[str] = mapped_column(String(64), nullable=False)
    os: Mapped[str] = mapped_column(String(64), nullable=False)

    # PII — never log or return in API responses
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cumulative_credits_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cumulative_credits_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reward_tier: Mapped[RewardTier] = mapped_column(
        Enum(RewardTier), nullable=False, default=RewardTier.bronze
    )
    iot_thing_name: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=func.now(),
    )
