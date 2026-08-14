"""requirement platform foundation

Revision ID: 20260814_0007
Revises: 20260531_0006
Create Date: 2026-08-14

The marketplace is intentionally isolated from ATS jobs and resumes. Shared
foreign keys are limited to users and organizations.
"""

from alembic import op

from backend.requirement_platform import models as rp_models  # noqa: F401
from backend.database import Base


revision = "20260814_0007"
down_revision = "20260531_0006"
branch_labels = None
depends_on = None


TABLES = [
    "rp_profiles",
    "rp_recruiter_details",
    "rp_hr_details",
    "rp_vendor_details",
    "rp_agency_details",
    "rp_profile_taxonomy_values",
    "rp_profile_capabilities",
    "rp_verifications",
    "rp_trust_scores",
    "rp_requirements",
    "rp_requirement_skills",
    "rp_source_requests",
    "rp_invitations",
    "rp_assignments",
    "rp_candidate_submissions",
    "rp_reports",
]


def upgrade():
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
