param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$required = @("Dockerfile", ".dockerignore", "requirements.txt", "src/main.py", "scripts/deploy-cloudrun.ps1", "scripts/bootstrap-gcp.ps1", "scripts/smoke-cloudrun.ps1", "scripts/verify-cloudrun.ps1")
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing deployment file: $path"
    }
}

$dockerIgnore = Get-Content .dockerignore -Raw
foreach ($entry in @(".env", ".venv", ".git", "tests")) {
    if ($dockerIgnore -notmatch [regex]::Escape($entry)) {
        throw ".dockerignore must exclude $entry"
    }
}

if ((Get-Content Dockerfile -Raw) -notmatch "USER sentinelops") {
    throw "Dockerfile must run the application as the non-root sentinelops user"
}

if ((Get-Content scripts/bootstrap-gcp.ps1 -Raw) -notmatch '\[switch\]\$Apply') {
    throw "bootstrap-gcp.ps1 must require explicit -Apply for cloud mutations"
}

if ((Get-Content scripts/bootstrap-gcp.ps1 -Raw) -notmatch 'already exists') {
    throw "bootstrap-gcp.ps1 must skip resources that already exist"
}

if ((Get-Content scripts/deploy-cloudrun.ps1 -Raw) -notmatch '--service-account') {
    throw "Cloud Run deployment must use the dedicated runtime service account"
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $python) {
    & $python -m compileall -q src
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed" }
}

Write-Host "Cloud configuration validation passed. Docker/gcloud execution was not required."
