param(
    [string]$Container = "production_level_resume_parser-copy-postgres-1",
    [string]$Database = "ats",
    [string]$User = "ats",
    [string]$OutputDir = ".\\backups"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $OutputDir "ats-$stamp.sql"

docker exec $Container pg_dump -U $User $Database | Set-Content -Path $target
Write-Host "Backup written to $target"
