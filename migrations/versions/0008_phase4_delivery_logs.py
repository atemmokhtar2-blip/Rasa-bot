"""Persist Telegram bot webhook secret references and delivery attempts.

Revision ID: 0008_phase4_delivery_logs
Revises: 0007_webhook_subscriptions
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_phase4_delivery_logs"
down_revision = "0007_webhook_subscriptions"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("bots", sa.Column("webhook_secret_ref", sa.String(length=255), nullable=True))
    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("webhook_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_delivery_logs_project_id", "webhook_delivery_logs", ["project_id"])
    op.create_index("ix_webhook_delivery_logs_webhook_id", "webhook_delivery_logs", ["webhook_id"])
    op.create_index("ix_webhook_delivery_logs_event_id", "webhook_delivery_logs", ["event_id"])
    op.create_index("ix_webhook_delivery_logs_created_at", "webhook_delivery_logs", ["created_at"])

def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_logs_created_at", table_name="webhook_delivery_logs")
    op.drop_index("ix_webhook_delivery_logs_event_id", table_name="webhook_delivery_logs")
    op.drop_index("ix_webhook_delivery_logs_webhook_id", table_name="webhook_delivery_logs")
    op.drop_index("ix_webhook_delivery_logs_project_id", table_name="webhook_delivery_logs")
    op.drop_table("webhook_delivery_logs")
    op.drop_column("bots", "webhook_secret_ref")
