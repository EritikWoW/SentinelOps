param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Region = "europe-west1",
    [string]$Service = "sentinelops",
    [ValidateSet("demo", "gemini")]
    [string]$Mode = "demo",
    [ValidateSet("memory", "firestore")]
    [string]$Store = "memory",
    [string]$ServiceAccount = "sentinelops-runtime",
    [string]$GoogleCloudLocation = "global",
    [switch]$EnablePubSub,
    [ValidateSet("pull", "push")]
    [string]$PubSubDeliveryMode = "push",
    [string]$Subscription = "sentinelops-incoming-sub",
    [string]$IncomingTopic = "sentinelops-incoming-events",
    [string]$InternalTopic = "sentinelops-internal-events",
    [string]$DeadLetterTopic = "sentinelops-dead-letter-events",
    [string]$PushServiceAccount = "sentinelops-pubsub-invoker",
    [string]$PushAudience = "",
    [switch]$RequireApiToken,
    [string]$ApiTokenSecret = "sentinelops-api-token"
)

$ErrorActionPreference = "Stop"

Write-Host "Configuring gcloud project: $ProjectId"
gcloud config set project $ProjectId
Write-Host "Enabling Cloud Run, Artifact Registry, Cloud Build, and Vertex AI APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com
Write-Host "Deploying $Service to Cloud Run in $Region"
$pubsubEnabled = if ($EnablePubSub) { "true" } else { "false" }
$authRequired = if ($RequireApiToken) { "true" } else { "false" }
$pushServiceAccountEmail = "$PushServiceAccount@$ProjectId.iam.gserviceaccount.com"
$envVars = "SENTINELOPS_MODE=$Mode,SENTINELOPS_STORE=$Store,SENTINELOPS_ENV=production,SENTINELOPS_AUTH_REQUIRED=$authRequired,PUBSUB_ENABLED=$pubsubEnabled,PUBSUB_DELIVERY_MODE=$PubSubDeliveryMode,PUBSUB_TOPIC=$IncomingTopic,PUBSUB_INTERNAL_TOPIC=$InternalTopic,PUBSUB_SUBSCRIPTION=$Subscription,PUBSUB_DEAD_LETTER_TOPIC=$DeadLetterTopic,PUBSUB_PUSH_SERVICE_ACCOUNT=$pushServiceAccountEmail,PUBSUB_PUSH_AUDIENCE=$PushAudience,FIRESTORE_DATABASE=(default),GOOGLE_CLOUD_PROJECT=$ProjectId,GOOGLE_CLOUD_LOCATION=$GoogleCloudLocation,GOOGLE_GENAI_USE_VERTEXAI=true"
$deployArgs = @(
    "run", "deploy", $Service,
    "--source", ".",
    "--region", $Region,
    "--platform", "managed",
    "--allow-unauthenticated",
    "--set-env-vars", $envVars,
    "--memory", "1Gi",
    "--cpu", "1",
    "--min", "0",
    "--max", "2",
    "--port", "8080",
    "--service-account", "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"
)
$secretBindings = @()
if ($RequireApiToken) {
    $secretBindings += "SENTINELOPS_API_TOKEN=${ApiTokenSecret}:latest"
}
if ($secretBindings.Count -gt 0) {
    $deployArgs += @("--set-secrets", ($secretBindings -join ","))
}
gcloud @deployArgs
Write-Host "Service URL:"
gcloud run services describe $Service --region $Region --format="value(status.url)"
