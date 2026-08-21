"""Add sourcing approval workflow.

Revision ID: 20260821_0015
Revises: 20260821_0014
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_0015"
down_revision = "20260821_0014"
branch_labels = None
depends_on = None


def _add(column):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("jobs") and column.name not in {item["name"] for item in inspector.get_columns("jobs")}:
        op.add_column("jobs", column)


def upgrade():
    _add(sa.Column("sourcing_approval_status", sa.String(), nullable=True))
    _add(sa.Column("sourcing_approval_token_hash", sa.String(), nullable=True))
    _add(sa.Column("sourcing_approved_at", sa.DateTime(), nullable=True))
    _add(sa.Column("sourcing_rejected_at", sa.DateTime(), nullable=True))
    _add(sa.Column("sourcing_request_source", sa.String(), nullable=True))
    bind = op.get_bind()
    if sa.inspect(bind).has_table("jobs"):
        bind.execute(sa.text("UPDATE jobs SET sourcing_approval_status = 'approved' WHERE sourcing_requested = true AND sourcing_approval_status IS NULL"))
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("jobs")}
        if "ix_jobs_sourcing_approval_status" not in indexes:
            op.create_index("ix_jobs_sourcing_approval_status", "jobs", ["sourcing_approval_status"])
        if "ix_jobs_sourcing_approval_token_hash" not in indexes:
            op.create_index("ix_jobs_sourcing_approval_token_hash", "jobs", ["sourcing_approval_token_hash"], unique=True)


def downgrade():
    pass
