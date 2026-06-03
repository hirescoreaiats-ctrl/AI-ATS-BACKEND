# Enterprise AI ATS Architecture

This project now preserves the existing FastAPI + vanilla JavaScript ATS while adding a production migration path.

## Backend

- `backend/api`: new versioned enterprise APIs for health, AI copilot, collaboration, search, and realtime updates.
- `backend/core`: environment-based settings, JWT security, RBAC, structured logging.
- `backend/middleware`: access logging, security headers, Redis-backed rate limiting with in-memory fallback.
- `backend/services`: existing AI parsing, semantic scoring, skill normalization, seniority inference, and explanations remain intact.
- `backend/ai`: vector search, pgvector setup, AI hiring summaries, rejection reasoning, and candidate similarity.
- `backend/repositories`: audit and activity persistence helpers.
- `backend/workers`: Celery worker scaffold for background AI jobs.
- `backend/models.py`: preserved SQLAlchemy registry with enterprise tables added for organizations, audit logs, notes, tags, timeline, interviews, scorecards, and offers.

## Frontend

- Existing HTML/CSS/vanilla JavaScript files remain available.
- React/Tailwind migration entrypoint is `frontend/enterprise.html`.
- Reusable ATS components live in `frontend/components`.
- Recruiter workspace layout, pipeline board, sticky data table, filters, analytics cards, AI insight panel, and interview scheduler are implemented.

## Production Services

- PostgreSQL target is configured through `DATABASE_URL`.
- pgvector is enabled in Alembic for PostgreSQL deployments.
- Redis powers Celery and rate limiting.
- Docker Compose includes API, worker, PostgreSQL with pgvector, Redis, and nginx.
- CI compiles backend and builds the React frontend.

## Migration Strategy

1. Keep running legacy endpoints and screens during migration.
2. Move new recruiter workflows to `/api/v1/*`.
3. Gradually point vanilla screens or the new React workspace at enterprise APIs.
4. Switch `DATABASE_URL` to PostgreSQL and run Alembic before production deployment.
