"""agency workflow notes tags and activity tables

Revision ID: 20260530_0004
Revises: 20260530_0003
Create Date: 2026-05-30
"""
from alembic import op

revision = "20260530_0004"
down_revision = "20260530_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_notes (
            id VARCHAR PRIMARY KEY,
            candidate_id VARCHAR NOT NULL,
            job_id VARCHAR,
            author_user_id VARCHAR,
            body TEXT NOT NULL,
            visibility VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_notes_candidate_id ON candidate_notes (candidate_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_notes_job_id ON candidate_notes (job_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_tags (
            id VARCHAR PRIMARY KEY,
            candidate_id VARCHAR NOT NULL,
            tag VARCHAR NOT NULL,
            color VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_tags_candidate_id ON candidate_tags (candidate_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_tag ON candidate_tags (candidate_id, tag)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_activities (
            id VARCHAR PRIMARY KEY,
            candidate_id VARCHAR NOT NULL,
            job_id VARCHAR,
            actor_user_id VARCHAR,
            activity_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            body TEXT,
            created_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_activities_candidate_id ON candidate_activities (candidate_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_activities_job_id ON candidate_activities (job_id)")


def downgrade():
    for table in ["candidate_activities", "candidate_tags", "candidate_notes"]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
