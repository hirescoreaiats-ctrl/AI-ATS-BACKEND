"""pilot access management

Revision ID: 20260815_0009
Revises: 20260624_0008
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa


revision = "20260815_0009"
down_revision = "20260624_0008"
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
    user_columns = [
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("pilot_started_at", sa.DateTime(), nullable=True),
        sa.Column("pilot_expires_at", sa.DateTime(), nullable=True),
        sa.Column("pilot_status", sa.String(), nullable=True),
        sa.Column("pilot_access_status", sa.String(), nullable=True),
        sa.Column("max_total_jobs", sa.Integer(), nullable=True),
        sa.Column("max_active_jobs", sa.Integer(), nullable=True),
        sa.Column("max_resumes_per_job", sa.Integer(), nullable=True),
        sa.Column("max_total_resumes", sa.Integer(), nullable=True),
        sa.Column("pilot_notes", sa.Text(), nullable=True),
        sa.Column("pilot_source", sa.String(), nullable=True),
        sa.Column("pilot_deactivated_at", sa.DateTime(), nullable=True),
        sa.Column("pilot_deactivated_by", sa.String(), nullable=True),
        sa.Column("pilot_deactivation_reason", sa.Text(), nullable=True),
        sa.Column("pilot_suspended_at", sa.DateTime(), nullable=True),
        sa.Column("pilot_suspended_by", sa.String(), nullable=True),
        sa.Column("pilot_suspension_reason", sa.Text(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
    ]
    for column in user_columns:
        _add_column_if_missing("users", column)
    _add_column_if_missing("recruiter_invitations", sa.Column("accepted_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("recruiter_invitations", sa.Column("pilot_config_json", sa.Text(), nullable=True))
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("pilot_resume_reservations"):
        op.create_table(
            "pilot_resume_reservations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("job_id", sa.String(), nullable=False),
            sa.Column("reserved_count", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        )
        op.create_index("ix_pilot_resume_reservations_user_id", "pilot_resume_reservations", ["user_id"])
        op.create_index("ix_pilot_resume_reservations_job_id", "pilot_resume_reservations", ["job_id"])
        op.create_index("ix_pilot_resume_reservations_expires_at", "pilot_resume_reservations", ["expires_at"])


def downgrade():
    pass
