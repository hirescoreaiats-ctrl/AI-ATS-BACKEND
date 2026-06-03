# HireScore AI Backend

FastAPI backend for HireScore AI resume screening, candidate ranking, outreach, and interview workflow.

## Production Target

- Backend hosting: DigitalOcean VPS
- Database: Supabase Postgres
- Resume object storage: Supabase Storage bucket
- Runtime: Docker Compose

## Required Supabase Setup

1. Create a Supabase project.
2. Copy the pooled Postgres connection string from Supabase.
3. Create a private Storage bucket named `resumes`.
4. Copy the service role key. Keep it server-side only.

## Environment

Copy:

```bash
cp .env.production.example .env.production
```

Set these important values:

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

## Run on VPS

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
docker compose exec api alembic upgrade head
```

API will be served through Caddy on ports `80` and `443`.

For the full DigitalOcean guide, see `deploy/digitalocean-vps.md`.

## Create Admin User

Run this on the production VPS after `.env` is configured:

```bash
cd /var/www/hirescore-ai-backend
source venv/bin/activate
export ADMIN_EMAIL="admin@example.com"
export ADMIN_NAME="Admin"
read -s ADMIN_PASSWORD
python scripts/create_admin_user.py
unset ADMIN_PASSWORD
```

## GitHub Push

```bash
git init
git add .
git commit -m "Initial backend repo"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/hirescore-backend.git
git push -u origin main
```
