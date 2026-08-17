"""Persist encrypted developer webhook subscriptions.

Revision ID: 0007_webhook_subscriptions
Revises: 0006_api_key_metadata
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_webhook_subscriptions"
down_revision = "0006_api_key_metadata"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("event_name", sa.String(length=128), nullable=False, index=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("timeout_seconds", sa.Float(), nullable=False, server_default="10"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("webhook_subscriptions")
