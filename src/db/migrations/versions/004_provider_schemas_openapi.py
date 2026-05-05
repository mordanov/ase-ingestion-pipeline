"""Evolve provider_schemas: add openapi fields, drop schema_type (for deployments that ran 003 before this change)

Revision ID: 004
Revises: 003
Create Date: 2026-05-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if _column_exists("provider_schemas", "schema_type"):
        op.drop_column("provider_schemas", "schema_type")

    if not _column_exists("provider_schemas", "openapi_url"):
        op.add_column("provider_schemas", sa.Column("openapi_url", sa.String(512), nullable=True))

    if not _column_exists("provider_schemas", "openapi_schema"):
        op.add_column(
            "provider_schemas", sa.Column("openapi_schema", postgresql.JSONB(), nullable=True)
        )

    if not _column_exists("provider_schemas", "request_mapping"):
        op.add_column(
            "provider_schemas",
            sa.Column(
                "request_mapping", postgresql.JSONB(), nullable=False, server_default="'{}'::jsonb"
            ),
        )

    if not _column_exists("provider_schemas", "response_mapping"):
        op.add_column(
            "provider_schemas",
            sa.Column(
                "response_mapping", postgresql.JSONB(), nullable=False, server_default="'{}'::jsonb"
            ),
        )


def downgrade() -> None:
    op.add_column(
        "provider_schemas",
        sa.Column("schema_type", sa.String(32), nullable=False, server_default="service1_schema"),
    )
    for col in ("openapi_url", "openapi_schema", "request_mapping", "response_mapping"):
        if _column_exists("provider_schemas", col):
            op.drop_column("provider_schemas", col)
