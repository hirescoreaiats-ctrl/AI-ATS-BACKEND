from __future__ import annotations

import os
import sys
from datetime import datetime

from backend.core.security import hash_password
from backend.database import SessionLocal
from backend.models import User


def required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def main() -> None:
    email = required_env("ADMIN_EMAIL").lower()
    password = required_env("ADMIN_PASSWORD")
    name = (os.getenv("ADMIN_NAME") or email.split("@", 1)[0]).strip()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.name = user.name or name
            user.password = hash_password(password)
            user.role = "admin"
            user.is_active = True
            user.subscription_status = "active"
            user.subscription_plan = user.subscription_plan or "manual"
            user.subscription_started_at = user.subscription_started_at or datetime.utcnow()
            action = "updated"
        else:
            user = User(
                name=name,
                email=email,
                password=hash_password(password),
                role="admin",
                is_active=True,
                subscription_status="active",
                subscription_plan="manual",
                subscription_started_at=datetime.utcnow(),
                auth_provider="email",
            )
            db.add(user)
            action = "created"

        db.commit()
        print(f"Admin user {action}: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
