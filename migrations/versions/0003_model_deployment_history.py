"""persist model deployment and rollback history
Revision ID: 0003_model_deployment_history
Revises: 0002_phase3_lineage
"""
from alembic import op

revision = "0003_model_deployment_history"
down_revision = "0002_phase3_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS deployment_history JSON NOT NULL DEFAULT '[]'::json")


def downgrade() -> None:
    op.execute("ALTER TABLE models DROP COLUMN IF EXISTS deployment_history")

