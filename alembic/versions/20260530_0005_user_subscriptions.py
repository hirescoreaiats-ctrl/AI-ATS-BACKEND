"""user subscription fields

Revision ID: 20260530_0005
Revises: 20260530_0004
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260530_0005"
down_revision = "20260530_0004"
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


def upgrade():
    _add_column_if_missing("users", sa.Column("subscription_status", sa.String(), server_default="unpaid", nullable=True))
    _add_column_if_missing("users", sa.Column("subscription_plan", sa.String(), nullable=True))
    _add_column_if_missing("users", sa.Column("subscription_started_at", sa.DateTime(), nullable=True))


def downgrade():
    pass
