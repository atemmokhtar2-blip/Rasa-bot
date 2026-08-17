"""persist dataset aggregate separate from immutable version rows
Revision ID: 0004_dataset_catalog
Revises: 0003_model_deployment_history
"""
from alembic import op

revision = "0004_dataset_catalog"
down_revision = "0003_model_deployment_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset_catalogs (
            id VARCHAR(64) PRIMARY KEY,
            project_id VARCHAR(64) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            language VARCHAR(32) NOT NULL DEFAULT 'ar',
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            schema_version VARCHAR(32) NOT NULL DEFAULT '1',
            current_version VARCHAR(64),
            metadata JSON NOT NULL DEFAULT '{}'::json,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_catalogs_project_id ON dataset_catalogs(project_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dataset_catalogs")
