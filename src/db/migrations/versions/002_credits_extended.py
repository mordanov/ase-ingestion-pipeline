"""Credits extended: streak/tier columns, credit_config table, transaction metadata

Revision ID: 002
Revises: 001
Create Date: 2026-05-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend devices table
    op.add_column("devices", sa.Column("streak_days", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("devices", sa.Column("last_activity_date", sa.Date(), nullable=True))
    op.add_column("devices", sa.Column("cumulative_credits_earned", sa.Integer(), nullable=False, server_default="0"))

    # Extend creditactiontype enum
    op.execute("ALTER TYPE creditactiontype ADD VALUE IF NOT EXISTS 'activity_reward'")
    op.execute("ALTER TYPE creditactiontype ADD VALUE IF NOT EXISTS 'streak_bonus'")
    op.execute("ALTER TYPE creditactiontype ADD VALUE IF NOT EXISTS 'adjustment'")
    op.execute("ALTER TYPE creditactiontype ADD VALUE IF NOT EXISTS 'tier_discount'")

    # Extend credit_transactions table
    op.add_column("credit_transactions", sa.Column("reason", sa.String(256), nullable=False, server_default=""))
    op.add_column("credit_transactions", sa.Column("metadata", postgresql.JSONB(), nullable=True))
    op.add_column("credit_transactions", sa.Column("event_id", sa.String(128), nullable=True))

    # Create credit_config table
    op.create_table(
        "credit_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_initial_balance", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("activity_earning_rules", postgresql.JSONB(), nullable=False),
        sa.Column("service_costs", postgresql.JSONB(), nullable=False),
        sa.Column("streak_bonus_7d", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("streak_bonus_30d", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("tier_thresholds", postgresql.JSONB(), nullable=False),
        sa.Column("tier_multipliers", postgresql.JSONB(), nullable=False),
        sa.Column("tier_discounts", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(128), nullable=False, server_default="system"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_config_is_active", "credit_config", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_credit_config_is_active", table_name="credit_config")
    op.drop_table("credit_config")

    op.drop_column("credit_transactions", "event_id")
    op.drop_column("credit_transactions", "metadata")
    op.drop_column("credit_transactions", "reason")

    op.drop_column("devices", "cumulative_credits_earned")
    op.drop_column("devices", "last_activity_date")
    op.drop_column("devices", "streak_days")
