"""ML tables: training jobs, trained models, anomaly readings, on-device packages

Revision ID: 005
Revises: 004
Create Date: 2026-05-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ml_trained_models — must exist before ml_training_jobs (FK)
    op.create_table(
        "ml_trained_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "model_type",
            sa.Enum("reranker", "anomaly_detector", name="modeltype"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("training_job_id", sa.String(64), nullable=False),
        sa.Column("artifact_path", sa.String(512), nullable=False),
        sa.Column("predecessor_id", sa.Integer(), nullable=True),
        sa.Column("ndcg_at_10", sa.Float(), nullable=True),
        sa.Column("f1_score", sa.Float(), nullable=True),
        sa.Column(
            "deployment_status",
            sa.Enum("active", "archived", "failed", name="modeldeploymentstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["predecessor_id"], ["ml_trained_models.id"]),
    )
    # Partial unique indexes: at most one active model per type
    op.execute(
        "CREATE UNIQUE INDEX ix_ml_trained_models_active_reranker "
        "ON ml_trained_models (model_type) "
        "WHERE deployment_status = 'active' AND model_type = 'reranker'"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_ml_trained_models_active_anomaly "
        "ON ml_trained_models (model_type) "
        "WHERE deployment_status = 'active' AND model_type = 'anomaly_detector'"
    )
    op.create_index("ix_ml_trained_models_type_version", "ml_trained_models", ["model_type", "version"])

    # ml_training_jobs
    op.create_table(
        "ml_training_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "succeeded", "failed", name="trainingjobstatus"),
            nullable=False,
            server_default="running",
        ),
        sa.Column("triggered_by", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(2048), nullable=True),
        sa.Column("reranker_model_id", sa.Integer(), nullable=True),
        sa.Column("anomaly_detector_model_id", sa.Integer(), nullable=True),
        sa.Column("reranker_ndcg_at_10", sa.Float(), nullable=True),
        sa.Column("anomaly_detector_f1", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["reranker_model_id"], ["ml_trained_models.id"]),
        sa.ForeignKeyConstraint(["anomaly_detector_model_id"], ["ml_trained_models.id"]),
    )
    # At most one running job at a time
    op.execute(
        "CREATE UNIQUE INDEX ix_ml_training_jobs_one_running "
        "ON ml_training_jobs (status) "
        "WHERE status = 'running'"
    )

    # ml_anomaly_readings
    op.create_table(
        "ml_anomaly_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("reading_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("threshold_exceeded", sa.Boolean(), nullable=False),
        sa.Column("evaluated_fields", postgresql.JSONB(), nullable=False),
        sa.Column("suppression_threshold", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
    )
    op.create_index(
        "ix_ml_anomaly_readings_device_ts",
        "ml_anomaly_readings",
        ["device_id", sa.text("reading_timestamp DESC")],
    )

    # ml_on_device_packages
    op.create_table(
        "ml_on_device_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reranker_model_id", sa.Integer(), nullable=False),
        sa.Column("anomaly_detector_model_id", sa.Integer(), nullable=False),
        sa.Column("package_path", sa.String(512), nullable=False),
        sa.Column("compatibility_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("distributed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["reranker_model_id"], ["ml_trained_models.id"]),
        sa.ForeignKeyConstraint(["anomaly_detector_model_id"], ["ml_trained_models.id"]),
    )


def downgrade() -> None:
    op.drop_table("ml_on_device_packages")
    op.drop_index("ix_ml_anomaly_readings_device_ts", table_name="ml_anomaly_readings")
    op.drop_table("ml_anomaly_readings")
    op.execute("DROP INDEX IF EXISTS ix_ml_training_jobs_one_running")
    op.drop_table("ml_training_jobs")
    op.execute("DROP INDEX IF EXISTS ix_ml_trained_models_active_reranker")
    op.execute("DROP INDEX IF EXISTS ix_ml_trained_models_active_anomaly")
    op.drop_index("ix_ml_trained_models_type_version", table_name="ml_trained_models")
    op.drop_table("ml_trained_models")
    op.execute("DROP TYPE IF EXISTS modeltype")
    op.execute("DROP TYPE IF EXISTS modeldeploymentstatus")
    op.execute("DROP TYPE IF EXISTS trainingjobstatus")
