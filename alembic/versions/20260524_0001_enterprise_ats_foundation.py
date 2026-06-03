"""enterprise ats foundation

Revision ID: 20260524_0001
Revises:
Create Date: 2026-05-24
"""
from alembic import context, op
import sqlalchemy as sa
from backend.ai.pgvector import PGVECTOR_DDL

revision = "20260524_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if context.get_context().dialect.name == "postgresql":
        op.execute(PGVECTOR_DDL)
    # Existing SQLite installs are protected by backend.main.ensure_resume_columns.
    # PostgreSQL deployments should run autogenerate after pointing DATABASE_URL to production.


def downgrade():
    pass
