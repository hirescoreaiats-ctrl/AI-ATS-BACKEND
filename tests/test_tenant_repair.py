from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Job, Organization, RecruiterInvitation, Resume, User
from backend.services.tenant_repair import repair_tenant_assignments


def test_shared_pilot_is_split_and_owned_data_follows_user():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        shared = Organization(id="shared", name="Admin Workspace", slug="admin-workspace")
        admin = User(id="admin", name="Admin", email="admin@example.com", password="hash", role="admin", organization_id=shared.id)
        pilot = User(id="pilot", name="Demo", email="demo@example.com", password="hash", role="recruiter", organization_id=shared.id, subscription_plan="pilot")
        admin_owned = Job(id="admin-job", job_title="Admin Job", organization_id=shared.id, owner_user_id=admin.id)
        pilot_owned = Job(id="pilot-job", job_title="Pilot Job", organization_id=shared.id, owner_user_id=pilot.id)
        legacy = Job(id="legacy-job", job_title="Legacy Admin Job", organization_id=None, owner_user_id=None)
        pilot_resume = Resume(id="pilot-resume", job_id=pilot_owned.id, organization_id=shared.id)
        invite = RecruiterInvitation(id="invite", organization_id=shared.id, invited_by_user_id=admin.id, email=pilot.email, token="pilot_token", status="accepted")
        db.add_all([shared, admin, pilot, admin_owned, pilot_owned, legacy, pilot_resume, invite])
        db.commit()

        result = repair_tenant_assignments(db)

        db.refresh(pilot)
        db.refresh(pilot_owned)
        db.refresh(pilot_resume)
        db.refresh(legacy)
        db.refresh(invite)
        assert result["pilots_split"] == 1
        assert pilot.organization_id != admin.organization_id
        assert pilot_owned.organization_id == pilot.organization_id
        assert pilot_resume.organization_id == pilot.organization_id
        assert invite.organization_id == pilot.organization_id
        assert admin_owned.organization_id == admin.organization_id
        assert legacy.organization_id == admin.organization_id

        second = repair_tenant_assignments(db)
        assert second["pilots_split"] == 0
    finally:
        db.close()
