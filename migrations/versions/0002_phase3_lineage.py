"""phase three dataset training model lineage
Revision ID: 0002_phase3_lineage
Revises: 0001_initial
"""
from alembic import op
revision = "0002_phase3_lineage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    statements = [
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS name VARCHAR(255)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS language VARCHAR(32) NOT NULL DEFAULT 'ar'",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS statistics JSON NOT NULL DEFAULT '{}'::json",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS checksum VARCHAR(128)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS created_by VARCHAR(64)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS metadata JSON NOT NULL DEFAULT '{}'::json",
        "ALTER TABLE models ADD COLUMN IF NOT EXISTS dataset_version VARCHAR(64)",
        "ALTER TABLE models ADD COLUMN IF NOT EXISTS training_job_id VARCHAR(64)",
        "ALTER TABLE models ADD COLUMN IF NOT EXISTS provider VARCHAR(64) NOT NULL DEFAULT 'rasa'",
        "ALTER TABLE models ADD COLUMN IF NOT EXISTS artifact_checksum VARCHAR(128)",
        "ALTER TABLE models ADD COLUMN IF NOT EXISTS evaluation_report JSON NOT NULL DEFAULT '{}'::json",
        "ALTER TABLE models ADD COLUMN IF NOT EXISTS deployment_environment VARCHAR(32)",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS error_code VARCHAR(64)",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS logs JSON NOT NULL DEFAULT '[]'::json",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS configuration JSON NOT NULL DEFAULT '{}'::json",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS framework_version VARCHAR(64)",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS provider_version VARCHAR(64)",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS rasa_version VARCHAR(64)",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS random_seed INTEGER",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
        "ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
    ]
    for statement in statements: op.execute(statement)

def downgrade() -> None:
    statements = [
        "ALTER TABLE datasets DROP COLUMN IF EXISTS name, DROP COLUMN IF EXISTS description, DROP COLUMN IF EXISTS language, DROP COLUMN IF EXISTS statistics, DROP COLUMN IF EXISTS checksum, DROP COLUMN IF EXISTS created_by, DROP COLUMN IF EXISTS metadata",
        "ALTER TABLE models DROP COLUMN IF EXISTS dataset_version, DROP COLUMN IF EXISTS training_job_id, DROP COLUMN IF EXISTS provider, DROP COLUMN IF EXISTS artifact_checksum, DROP COLUMN IF EXISTS evaluation_report, DROP COLUMN IF EXISTS deployment_environment",
        "ALTER TABLE training_jobs DROP COLUMN IF EXISTS error_code, DROP COLUMN IF EXISTS logs, DROP COLUMN IF EXISTS configuration, DROP COLUMN IF EXISTS framework_version, DROP COLUMN IF EXISTS provider_version, DROP COLUMN IF EXISTS rasa_version, DROP COLUMN IF EXISTS random_seed, DROP COLUMN IF EXISTS started_at, DROP COLUMN IF EXISTS completed_at",
    ]
    for statement in statements: op.execute(statement)
