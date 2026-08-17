"""Specification 06 training lifecycle fields.

Revision ID: 0009_spec06_training_lifecycle
Revises: 0008_phase4_delivery_logs
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_spec06_training_lifecycle"
down_revision = "0008_phase4_delivery_logs"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("training_jobs", sa.Column("request_id", sa.String(length=128), nullable=True))
    op.add_column("training_jobs", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("training_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("training_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("training_jobs", sa.Column("current_stage", sa.String(length=64), nullable=True))
    op.add_column("training_jobs", sa.Column("progress", sa.Float(), nullable=False, server_default="0"))
    op.add_column("training_jobs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("training_jobs", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
    op.create_index("ix_training_jobs_request_id", "training_jobs", ["request_id"])
    op.create_index("ix_training_jobs_worker_id", "training_jobs", ["worker_id"])
    op.create_unique_constraint("uq_training_jobs_idempotency_key", "training_jobs", ["idempotency_key"])

def downgrade() -> None:
    op.drop_constraint("uq_training_jobs_idempotency_key", "training_jobs", type_="unique")
    op.drop_index("ix_training_jobs_worker_id", table_name="training_jobs")
    op.drop_index("ix_training_jobs_request_id", table_name="training_jobs")
    op.drop_column("training_jobs", "max_retries")
    op.drop_column("training_jobs", "retry_count")
    op.drop_column("training_jobs", "progress")
    op.drop_column("training_jobs", "current_stage")
    op.drop_column("training_jobs", "heartbeat_at")
    op.drop_column("training_jobs", "worker_id")
    op.drop_column("training_jobs", "idempotency_key")
    op.drop_column("training_jobs", "request_id")
