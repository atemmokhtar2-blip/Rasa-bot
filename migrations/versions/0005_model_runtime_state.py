"""persist model runtime lifecycle state
Revision ID: 0005_model_runtime_state
Revises: 0004_dataset_catalog
"""
from alembic import op
revision = "0005_model_runtime_state"
down_revision = "0004_dataset_catalog"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS runtime_state JSON NOT NULL DEFAULT '{}'::json")

def downgrade() -> None:
    op.execute("ALTER TABLE models DROP COLUMN IF EXISTS runtime_state")
