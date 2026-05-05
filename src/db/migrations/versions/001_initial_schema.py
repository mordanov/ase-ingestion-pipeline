"""Initial schema: all tables

Revision ID: 001
Revises:
Create Date: 2026-05-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # devices
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column(
            "device_type",
            sa.Enum("smartwatch", "fitness_tracker", "smartphone", "laptop", name="devicetype"),
            nullable=False,
        ),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("firmware_version", sa.String(64), nullable=False),
        sa.Column("os", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("credit_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cumulative_credits_spent", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "reward_tier",
            sa.Enum("bronze", "silver", "gold", "platinum", name="rewardtier"),
            nullable=False,
            server_default="bronze",
        ),
        sa.Column("iot_thing_name", sa.String(128), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
        sa.UniqueConstraint("iot_thing_name"),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"])

    # ingestion_batches
    op.create_table(
        "ingestion_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("batch_id", sa.String(128), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "processing_status",
            sa.Enum(
                "pending", "processing", "completed", "failed", name="batchstatus"
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index("ix_ingestion_batches_device_id", "ingestion_batches", ["device_id"])

    # telemetry_events
    op.create_table(
        "telemetry_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column(
            "source_protocol",
            sa.Enum("http", "mqtt", name="sourceprotocol"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "validation_status",
            sa.Enum("valid", "invalid", "stale", name="validationstatus"),
            nullable=False,
            server_default="valid",
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["ingestion_batches.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_telemetry_events_device_id_received_at", "telemetry_events", ["device_id", "received_at"])

    # recommendation_requests
    op.create_table(
        "recommendation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("providers_called", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("providers_succeeded", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_requests_device_id", "recommendation_requests", ["device_id"])

    # credit_transactions
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(
                "recommendation", "registration_bonus", "top_up", name="creditactiontype"
            ),
            nullable=False,
        ),
        sa.Column("resulting_balance", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_transactions_device_id", "credit_transactions", ["device_id"])

    # quarantine_records
    op.create_table(
        "quarantine_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=False),
        sa.Column("source_protocol", sa.String(16), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column(
            "quarantined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quarantine_records_device_id", "quarantine_records", ["device_id"])


def downgrade() -> None:
    op.drop_table("quarantine_records")
    op.drop_table("credit_transactions")
    op.drop_table("recommendation_requests")
    op.drop_table("telemetry_events")
    op.drop_table("ingestion_batches")
    op.drop_table("devices")
    op.execute("DROP TYPE IF EXISTS devicetype")
    op.execute("DROP TYPE IF EXISTS rewardtier")
    op.execute("DROP TYPE IF EXISTS batchstatus")
    op.execute("DROP TYPE IF EXISTS sourceprotocol")
    op.execute("DROP TYPE IF EXISTS validationstatus")
    op.execute("DROP TYPE IF EXISTS creditactiontype")
