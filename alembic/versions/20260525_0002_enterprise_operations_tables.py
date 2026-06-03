"""enterprise operations tables

Revision ID: 20260525_0002
Revises: 20260524_0001
Create Date: 2026-05-25
"""
from alembic import op

revision = "20260525_0002"
down_revision = "20260524_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            department VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_members (
            id VARCHAR PRIMARY KEY,
            team_id VARCHAR NOT NULL,
            user_id VARCHAR NOT NULL,
            role VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_team_member ON team_members (team_id, user_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recruiter_invitations (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR NOT NULL,
            invited_by_user_id VARCHAR,
            email VARCHAR NOT NULL,
            role VARCHAR,
            status VARCHAR,
            token VARCHAR NOT NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_recruiter_invitations_token ON recruiter_invitations (token)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_stages (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR,
            job_id VARCHAR,
            key VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            position INTEGER,
            rules_json TEXT,
            is_terminal BOOLEAN,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_stage_history (
            id VARCHAR PRIMARY KEY,
            candidate_id VARCHAR NOT NULL,
            job_id VARCHAR,
            from_stage VARCHAR,
            to_stage VARCHAR NOT NULL,
            actor_user_id VARCHAR,
            reason TEXT,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_automations (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR,
            job_id VARCHAR,
            trigger_stage VARCHAR NOT NULL,
            action_type VARCHAR NOT NULL,
            config_json TEXT,
            is_active BOOLEAN,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_searches (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR,
            owner_user_id VARCHAR,
            name VARCHAR NOT NULL,
            query TEXT NOT NULL,
            filters_json TEXT,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_pools (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR,
            owner_user_id VARCHAR,
            name VARCHAR NOT NULL,
            description TEXT,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_pool_candidates (
            id VARCHAR PRIMARY KEY,
            talent_pool_id VARCHAR NOT NULL,
            candidate_id VARCHAR NOT NULL,
            added_by_user_id VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_talent_pool_candidate ON talent_pool_candidates (talent_pool_id, candidate_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_kits (
            id VARCHAR PRIMARY KEY,
            organization_id VARCHAR,
            job_id VARCHAR,
            name VARCHAR NOT NULL,
            competencies_json TEXT,
            questions_json TEXT,
            scorecard_template_json TEXT,
            created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS offer_approvals (
            id VARCHAR PRIMARY KEY,
            offer_id VARCHAR NOT NULL,
            approver_user_id VARCHAR,
            step_order INTEGER,
            status VARCHAR,
            notes TEXT,
            decided_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """
    )


def downgrade():
    for table in [
        "offer_approvals",
        "interview_kits",
        "talent_pool_candidates",
        "talent_pools",
        "saved_searches",
        "pipeline_automations",
        "candidate_stage_history",
        "pipeline_stages",
        "recruiter_invitations",
        "team_members",
        "teams",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
