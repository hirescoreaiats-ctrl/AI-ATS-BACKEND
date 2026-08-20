"""Add optional company website to jobs.

Revision ID: 20260821_0014
Revises: 20260821_0013
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_0014"
down_revision = "20260821_0013"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("jobs"):
        return
    existing = {item["name"] for item in inspector.get_columns("jobs")}
    if "company_website" not in existing:
        op.add_column("jobs", sa.Column("company_website", sa.String(), nullable=True))


def downgrade():
    pass
