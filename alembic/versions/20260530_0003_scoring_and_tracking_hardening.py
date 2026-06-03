"""scoring and tracking hardening columns

Revision ID: 20260530_0003
Revises: 20260525_0002
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260530_0003"
down_revision = "20260525_0002"
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
    _add_column_if_missing("jobs", sa.Column("preferred_skills", sa.Text(), nullable=True))

    _add_column_if_missing("resumes", sa.Column("rank_score", sa.Float(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("fit_band", sa.String(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("confidence_score", sa.Float(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("resume_quality_score", sa.Float(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("ai_recommendation", sa.String(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("ranking_reason", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("ai_confidence_reason", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("projects", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("resume_file_path", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("resume_original_filename", sa.String(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("resume_content_type", sa.String(), nullable=True))


def downgrade():
    pass
