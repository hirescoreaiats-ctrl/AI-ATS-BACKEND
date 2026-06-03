# HireScore AI ATS Production

Single GitHub repository with separate deployable apps:

- `backend/` - FastAPI backend for DigitalOcean VPS
- `frontend/` - static frontend for separate frontend hosting

## Backend Hosting

Deploy `backend/` on DigitalOcean VPS.

Backend uses:

- FastAPI
- Celery worker
- Redis
- Supabase Postgres
- Supabase Storage bucket for uploaded resumes

Backend env file:

```bash
cd backend
cp .env.production.example .env.production
```

Important backend variables:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@SUPABASE_POOLER_HOST:6543/postgres?sslmode=require
STORAGE_BACKEND=supabase
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=resumes
FRONTEND_URL=https://your-frontend-domain.com
ALLOWED_ORIGINS=https://your-frontend-domain.com
JWT_SECRET=use-a-long-random-secret
OPENAI_API_KEY=your-openai-key
```

Run backend on VPS:

```bash
cd backend
docker compose up -d --build
docker compose exec api alembic upgrade head
```

## Frontend Hosting

Deploy `frontend/` as a static website.

Edit `frontend/runtime-config.js`:

```js
window.__HIRESCORE_API_BASE__ = "https://your-backend-domain.com";
```

Main production page:

```text
frontend/index.html
```

## GitHub Push

Create a new empty GitHub repository under `hirescoreaiats-ctrl`, then run:

```bash
git remote add origin https://github.com/hirescoreaiats-ctrl/YOUR_NEW_REPO_NAME.git
git push -u origin main
```
