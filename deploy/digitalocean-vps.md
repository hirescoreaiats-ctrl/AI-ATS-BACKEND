# DigitalOcean VPS Backend Deploy

Use this guide for the `AI-ATS-BACKEND` repository on an Ubuntu Droplet.

## 1. Create the Droplet

- Image: Ubuntu LTS
- Size: minimum 2 GB RAM recommended for API + worker + Redis
- Authentication: SSH key preferred
- Firewall: allow SSH, HTTP, and HTTPS

DigitalOcean docs:
- Create Droplet: https://docs.digitalocean.com/products/droplets/how-to/create/
- Connect with SSH: https://docs.digitalocean.com/products/droplets/how-to/connect-with-ssh/
- Cloud Firewall: https://docs.digitalocean.com/products/networking/firewalls/how-to/create/

## 2. Point DNS

Create an `A` record:

```text
api.your-domain.com -> DROPLET_PUBLIC_IP
```

This is required for automatic HTTPS with Caddy.

## 3. Install server tools

SSH into the VPS:

```bash
ssh root@DROPLET_PUBLIC_IP
```

Install Docker, Git, and firewall rules:

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## 4. Clone backend repo

```bash
mkdir -p /opt/hirescore
cd /opt/hirescore
git clone https://github.com/hirescoreaiats-ctrl/AI-ATS-BACKEND.git
cd AI-ATS-BACKEND
```

For private repos, GitHub may ask for your username and a personal access token.

## 5. Configure environment

```bash
cp .env.production.example .env.production
nano .env.production
```

Set the real values:

```env
API_DOMAIN=api.your-domain.com
APP_PUBLIC_BASE_URL=https://api.your-domain.com
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@SUPABASE_POOLER_HOST:6543/postgres?sslmode=require
REDIS_URL=redis://redis:6379/0
STORAGE_BACKEND=supabase
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=resumes
ALLOWED_ORIGINS=https://your-frontend-domain.com
FRONTEND_URL=https://your-frontend-domain.com
JWT_SECRET=LONG_RANDOM_SECRET
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
SECURE_COOKIES=true
```

Keep `.env.production` private. Do not commit it.

## 6. Start backend with HTTPS

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
docker compose exec api alembic upgrade head
```

Check status:

```bash
docker compose ps
curl https://api.your-domain.com/api/v1/health
curl https://api.your-domain.com/api/v1/health/ready
```

## 7. Update deployment after code changes

```bash
cd /opt/hirescore/AI-ATS-BACKEND
git pull
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
docker compose exec api alembic upgrade head
```

## Temporary IP-only test

If DNS is not ready yet, run without Caddy:

```bash
docker compose up -d --build
curl http://DROPLET_PUBLIC_IP:8000/api/v1/health
```

For production, use domain + HTTPS.
