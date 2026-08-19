"""Add canonical candidate ranking freshness metadata.

Revision ID: 20260819_0012
Revises: 20260818_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0012"
down_revision = "20260818_0011"
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
    _add_column_if_missing("resumes", sa.Column("ranking_version", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("resumes", sa.Column("ranking_updated_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("manual_overrides_json", sa.Text(), nullable=True))
    _create_index_if_missing("resumes", "ix_resumes_ranking_version", ["ranking_version"])
    _create_index_if_missing("resumes", "ix_resumes_ranking_updated_at", ["ranking_updated_at"])


def downgrade():
    pass
