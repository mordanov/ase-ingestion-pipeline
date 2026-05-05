import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ProviderSchema(Base):
    __tablename__ = "provider_schemas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    # Full OpenAPI spec stored for reference and re-editing
    openapi_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    openapi_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # How to build the POST body: {fields: {dotted.path: {source, transform?, value?}}}
    request_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # How to extract recommendations from the response
    response_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
