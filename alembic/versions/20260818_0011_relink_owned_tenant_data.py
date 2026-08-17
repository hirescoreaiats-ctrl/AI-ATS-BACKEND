"""Relink owned jobs and resumes to the owner's workspace.

Revision ID: 20260818_0011
Revises: 20260817_0010
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0011"
down_revision = "20260817_0010"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE jobs SET organization_id = ("
        "SELECT users.organization_id FROM users WHERE users.id = jobs.owner_user_id"
        ") WHERE owner_user_id IS NOT NULL AND EXISTS ("
        "SELECT 1 FROM users WHERE users.id = jobs.owner_user_id AND users.organization_id IS NOT NULL)"
    ))
    bind.execute(sa.text(
        "UPDATE resumes SET organization_id = ("
        "SELECT jobs.organization_id FROM jobs WHERE jobs.id = resumes.job_id"
        ") WHERE EXISTS ("
        "SELECT 1 FROM jobs WHERE jobs.id = resumes.job_id AND jobs.organization_id IS NOT NULL)"
    ))


def downgrade():
    pass
