param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$Database = "ats",
    [string]$AppUser = "ats",
    [string]$AppPassword = "ats",
    [string]$AdminUser = "postgres",
    [string]$AdminPassword = "",
    [switch]$MigrateSqlite
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $ProjectRoot ".env"
$VenvPython = "C:\Users\ASUS\Desktop\python code for my project\Fast APi\fastapienv\Scripts\python.exe"

function Find-Psql {
    $cmd = Get-Command psql -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL" -Recurse -Filter psql.exe -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($candidates) { return $candidates[0].FullName }

    throw "psql.exe was not found. Install PostgreSQL first, then rerun this script."
}

function Upsert-EnvValue($Path, $Key, $Value) {
    $line = "$Key=$Value"
    if (!(Test-Path $Path)) {
        Set-Content -Path $Path -Value $line
        return
    }

    $content = Get-Content -Path $Path
    $found = $false
    $updated = foreach ($item in $content) {
        if ($item -match "^$([regex]::Escape($Key))=") {
            $found = $true
            $line
        } else {
            $item
        }
    }
    if (!$found) {
        $updated += $line
    }
    Set-Content -Path $Path -Value $updated
}

$psql = Find-Psql
$env:PGPASSWORD = $AdminPassword

Write-Host "Creating PostgreSQL role and database if needed..."
& $psql -h $HostName -p $Port -U $AdminUser -d postgres -v ON_ERROR_STOP=1 -c "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$AppUser') THEN CREATE ROLE $AppUser LOGIN PASSWORD '$AppPassword'; END IF; END `$`$;"

$dbExists = & $psql -h $HostName -p $Port -U $AdminUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$Database'"
if (("$dbExists").Trim() -ne "1") {
    & $psql -h $HostName -p $Port -U $AdminUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database OWNER $AppUser;"
}
& $psql -h $HostName -p $Port -U $AdminUser -d $Database -c "DO `$`$ BEGIN CREATE EXTENSION IF NOT EXISTS vector; EXCEPTION WHEN undefined_file OR feature_not_supported THEN RAISE NOTICE 'pgvector extension is not installed locally; JSON embedding fallback remains enabled.'; END `$`$;"

$databaseUrl = "postgresql+psycopg://$AppUser`:$AppPassword@$HostName`:$Port/$Database"
Upsert-EnvValue -Path $EnvPath -Key "DATABASE_URL" -Value $databaseUrl
Upsert-EnvValue -Path $EnvPath -Key "REDIS_URL" -Value "redis://localhost:6379/0"

Write-Host "Running Alembic migrations..."
Push-Location $ProjectRoot
try {
    & $VenvPython -c "from backend.database import engine; from backend.models import Base; Base.metadata.create_all(bind=engine)"
    & $VenvPython -m alembic upgrade head
    if ($MigrateSqlite) {
        & $VenvPython scripts/migrate_sqlite_to_postgres.py --sqlite resume_ai.db --database-url $databaseUrl
    }
}
finally {
    Pop-Location
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host "PostgreSQL configured. Restart uvicorn so the API picks up DATABASE_URL."
