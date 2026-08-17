"""expand API key metadata
Revision ID: 0006_api_key_metadata
Revises: 0005_model_runtime_state
"""
from alembic import op
revision = "0006_api_key_metadata"
down_revision = "0005_model_runtime_state"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS name VARCHAR(255) NOT NULL DEFAULT 'default'")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS prefix VARCHAR(64) NOT NULL DEFAULT 'adf_development_'")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_type VARCHAR(32) NOT NULL DEFAULT 'development'")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS metadata JSON NOT NULL DEFAULT '{}'::json")

def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS key_type")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS prefix")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS name")
