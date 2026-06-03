Enterprise model package placeholder.

The active SQLAlchemy registry remains in `backend/models.py` to preserve the
existing import path used by legacy routers. When the project is ready for a
larger migration, split that registry into this package and update imports in a
single Alembic-backed change.
