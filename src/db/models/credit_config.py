import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CreditConfig(Base):
    __tablename__ = "credit_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    default_initial_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    activity_earning_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    service_costs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    streak_bonus_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    streak_bonus_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    tier_thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tier_multipliers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tier_discounts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
