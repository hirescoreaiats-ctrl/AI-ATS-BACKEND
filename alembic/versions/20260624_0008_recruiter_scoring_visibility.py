"""recruiter scoring visibility fields

Revision ID: 20260624_0008
Revises: 20260612_0007
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260624_0008"
down_revision = "20260612_0007"
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
    _add_column_if_missing("resumes", sa.Column("shortlist_decision", sa.String(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("decision_reason", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("recruiter_explanation", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("strengths", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("concerns", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("score_breakdown", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("parser_confidence", sa.Float(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("parser_warnings", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("ai_parse_status", sa.String(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("extraction_quality_score", sa.Float(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("low_confidence_fields", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("missing_critical_skills", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("matched_critical_skills", sa.Text(), nullable=True))
    _add_column_if_missing("resumes", sa.Column("cap_reason", sa.Text(), nullable=True))

    _create_index_if_missing("resumes", "ix_resumes_job_id", ["job_id"])
    _create_index_if_missing("resumes", "ix_resumes_shortlist_decision", ["shortlist_decision"])


def downgrade():
    pass
