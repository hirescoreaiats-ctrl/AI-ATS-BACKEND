"""Give every existing tenantless non-admin account its own empty organization.

Revision ID: 20260817_0010
Revises: 20260815_0009
"""

from __future__ import annotations

import re
import uuid

from alembic import op
import sqlalchemy as sa

revision = "20260817_0010"
down_revision = "20260815_0009"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    users = bind.execute(sa.text(
        "SELECT id, name, email FROM users WHERE organization_id IS NULL "
        "AND COALESCE(role, 'recruiter') != 'super_admin'"
    )).mappings().all()
    for user in users:
        organization_id = str(uuid.uuid4())
        label = (user["name"] or str(user["email"]).split("@", 1)[0] or "Workspace").strip()
        slug_base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:70] or "workspace"
        bind.execute(sa.text(
            "INSERT INTO organizations (id, name, slug, plan, created_at) "
            "VALUES (:id, :name, :slug, :plan, CURRENT_TIMESTAMP)"
        ), {"id": organization_id, "name": f"{label} Workspace", "slug": f"{slug_base}-{uuid.uuid4().hex[:12]}", "plan": "pilot"})
        bind.execute(sa.text("UPDATE users SET organization_id = :organization_id WHERE id = :user_id"),
                     {"organization_id": organization_id, "user_id": user["id"]})


def downgrade():
    pass
