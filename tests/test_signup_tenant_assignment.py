from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.models import Base, Organization, User
from backend.routers.auth import _ensure_user_organization


def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_independent_users_receive_distinct_workspaces():
    db = session()
    first = User(name="Client A", email="a@example.com", password="hash", role="recruiter")
    second = User(name="Client B", email="b@example.com", password="hash", role="recruiter")
    db.add_all([first, second])

    first_org = _ensure_user_organization(db, first)
    second_org = _ensure_user_organization(db, second)
    db.commit()

    assert first_org
    assert second_org
    assert first_org != second_org
    assert db.query(Organization).count() == 2


def test_invited_user_keeps_assigned_workspace():
    db = session()
    organization = Organization(name="Existing Client", slug="existing-client")
    db.add(organization)
    db.flush()
    user = User(name="Invited", email="invite@example.com", password="hash", role="recruiter", organization_id=organization.id)
    db.add(user)

    assert _ensure_user_organization(db, user) == organization.id
    assert db.query(Organization).count() == 1
