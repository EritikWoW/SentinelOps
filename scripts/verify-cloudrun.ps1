param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Region = "europe-west1",
    [string]$Service = "sentinelops",
    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is required for Cloud Run verification."
}

gcloud config set project $ProjectId | Out-Null
$serviceUrl = if ($BaseUrl) {
    $BaseUrl.TrimEnd("/")
} else {
    (gcloud run services describe $Service --region $Region --format="value(status.url)").TrimEnd("/")
}
if (-not $serviceUrl) { throw "Cloud Run service URL is empty" }

$serviceAccount = gcloud run services describe $Service --region $Region --format="value(spec.template.spec.serviceAccountName)"
$health = Invoke-RestMethod -Uri "$serviceUrl/health"
$ready = Invoke-RestMethod -Uri "$serviceUrl/ready"
$settings = Invoke-RestMethod -Uri "$serviceUrl/settings"

if ($health.status -ne "ok") { throw "Liveness endpoint failed" }
if ($ready.status -ne "ready") { throw "Readiness endpoint failed" }
if ($settings.api_key_configured -ne $true -and $ready.mode -eq "gemini") {
    throw "Gemini mode is active but the runtime reports no configured API key"
}

[pscustomobject]@{
    project = $ProjectId
    service = $Service
    url = $serviceUrl
    service_account = $serviceAccount
    health = $health.status
    readiness = $ready.status
    mode = $ready.mode
    store = $ready.store
    pubsub_enabled = $ready.pubsub_enabled
    api_key_configured = $settings.api_key_configured
    verified_at = (Get-Date).ToUniversalTime().ToString("o")
}
