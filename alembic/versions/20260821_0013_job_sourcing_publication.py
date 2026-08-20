"""Persist ATS job sourcing publication state.

Revision ID: 20260821_0013
Revises: 20260819_0012
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_0013"
down_revision = "20260819_0012"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def upgrade():
    _add_column_if_missing("jobs", sa.Column("sourcing_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("jobs", sa.Column("sourcing_requested_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("sourcing_email_status", sa.String(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("sourcing_email_error", sa.Text(), nullable=True))
    _create_index_if_missing("jobs", "ix_jobs_sourcing_requested", ["sourcing_requested"])
    _create_index_if_missing("jobs", "ix_jobs_sourcing_requested_at", ["sourcing_requested_at"])


def downgrade():
    pass
