"""initial framework schema

Revision ID: 0001_initial
Revises:
"""
from pathlib import Path
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "001_initial.sql"
    for statement in sql_path.read_text(encoding="utf-8").split(";"):
        statement = statement.strip()
        if statement: op.execute(statement)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_events, training_jobs, bots, models, datasets, sessions, api_keys, audit_logs, projects, developers CASCADE")
