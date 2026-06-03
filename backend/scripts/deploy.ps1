param(
    [string]$Environment = "staging"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Enterprise AI ATS for $Environment"
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml run --rm api alembic upgrade head
docker compose -f docker-compose.yml up -d
Write-Host "Deployment started. Check health at http://localhost:8000/api/v1/health"
