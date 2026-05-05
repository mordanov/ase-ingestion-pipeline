import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CreditActionType(str, enum.Enum):
    recommendation = "recommendation"
    registration_bonus = "registration_bonus"
    top_up = "top_up"
    activity_reward = "activity_reward"
    streak_bonus = "streak_bonus"
    adjustment = "adjustment"
    tier_discount = "tier_discount"


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[CreditActionType] = mapped_column(Enum(CreditActionType), nullable=False)
    resulting_balance: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
