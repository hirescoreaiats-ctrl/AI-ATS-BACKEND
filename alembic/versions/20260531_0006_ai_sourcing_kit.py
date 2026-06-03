"""ai sourcing kit fields

Revision ID: 20260531_0006
Revises: 20260530_0005
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa

revision = "20260531_0006"
down_revision = "20260530_0005"
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


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade():
    _add_column_if_missing("jobs", sa.Column("public_apply_enabled", sa.Boolean(), server_default=sa.true(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("source_tracking_enabled", sa.Boolean(), server_default=sa.true(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("apply_slug", sa.String(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("generated_linkedin_post", sa.Text(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("generated_whatsapp_message", sa.Text(), nullable=True))
    _add_column_if_missing("jobs", sa.Column("generated_naukri_text", sa.Text(), nullable=True))
    _create_index_if_missing("jobs", "ix_jobs_apply_slug", ["apply_slug"], unique=True)

    _add_column_if_missing("resumes", sa.Column("application_source", sa.String(), server_default="direct", nullable=True))
    _add_column_if_missing("resumes", sa.Column("apply_tracking_url", sa.Text(), nullable=True))


def downgrade():
    pass
