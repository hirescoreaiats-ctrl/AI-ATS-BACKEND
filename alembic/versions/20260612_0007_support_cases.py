"""support cases

Revision ID: 20260612_0007
Revises: 20260531_0006
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20260612_0007"
down_revision = "20260531_0006"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("support_cases"):
        return
    op.create_table(
        "support_cases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="open", nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_support_cases_user_id", "support_cases", ["user_id"])
    op.create_index("ix_support_cases_email", "support_cases", ["email"])
    op.create_index("ix_support_cases_issue_type", "support_cases", ["issue_type"])
    op.create_index("ix_support_cases_priority", "support_cases", ["priority"])
    op.create_index("ix_support_cases_status", "support_cases", ["status"])
    op.create_index("ix_support_cases_created_at", "support_cases", ["created_at"])


def downgrade():
    op.drop_table("support_cases")
