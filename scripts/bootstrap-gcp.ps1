param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Region = "europe-west1",
    [string]$ServiceAccount = "sentinelops-runtime",
    [string]$SecretName = "sentinelops-gemini-api-key",
    [switch]$CreateSecret,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if ($Apply -and -not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is required. Install Google Cloud CLI and run 'gcloud auth login' first."
}

$serviceAccountEmail = "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"
$incomingTopic = "sentinelops-incoming-events"
$internalTopic = "sentinelops-internal-events"
$deadLetterTopic = "sentinelops-dead-letter-events"
$subscription = "sentinelops-incoming-sub"
$deadLetterSubscription = "sentinelops-dead-letter-sub"

function Invoke-GCloud {
    param([string[]]$Arguments)
    if ($Apply) {
        & gcloud @Arguments
        if ($LASTEXITCODE -ne 0) { throw "gcloud command failed: gcloud $($Arguments -join ' ')" }
    } else {
        Write-Host ("PLAN: gcloud " + ($Arguments -join " ")) -ForegroundColor DarkCyan
    }
}

function Test-GCloudResource {
    param([string[]]$Arguments)
    & gcloud @Arguments *> $null
    return $LASTEXITCODE -eq 0
}

function Ensure-GCloudResource {
    param(
        [string]$Label,
        [string[]]$DescribeArguments,
        [string[]]$CreateArguments
    )
    if (-not $Apply) {
        Invoke-GCloud $CreateArguments
        return
    }
    if (Test-GCloudResource $DescribeArguments) {
        Write-Host "SKIP: $Label already exists" -ForegroundColor DarkGray
        return
    }
    Invoke-GCloud $CreateArguments
}

Write-Host "SentinelOps Google Cloud bootstrap for $ProjectId / $Region" -ForegroundColor Cyan
if ($Apply) {
    Write-Host "Apply mode: cloud resources will be changed." -ForegroundColor Yellow
} else {
    Write-Host "Plan mode: no cloud resources will be changed." -ForegroundColor DarkCyan
}

Invoke-GCloud @("config", "set", "project", $ProjectId)
Invoke-GCloud @("services", "enable", "run.googleapis.com", "artifactregistry.googleapis.com", "cloudbuild.googleapis.com", "firestore.googleapis.com", "pubsub.googleapis.com", "secretmanager.googleapis.com")

Ensure-GCloudResource "Firestore (default)" @("firestore", "databases", "describe", "--database=(default)") @("firestore", "databases", "create", "--database=(default)", "--location=$Region", "--type=firestore-native")
Ensure-GCloudResource "Pub/Sub incoming topic $incomingTopic" @("pubsub", "topics", "describe", $incomingTopic) @("pubsub", "topics", "create", $incomingTopic)
Ensure-GCloudResource "Pub/Sub internal topic $internalTopic" @("pubsub", "topics", "describe", $internalTopic) @("pubsub", "topics", "create", $internalTopic)
Ensure-GCloudResource "Pub/Sub dead-letter topic $deadLetterTopic" @("pubsub", "topics", "describe", $deadLetterTopic) @("pubsub", "topics", "create", $deadLetterTopic)
Ensure-GCloudResource "Pub/Sub subscription $subscription" @("pubsub", "subscriptions", "describe", $subscription) @("pubsub", "subscriptions", "create", $subscription, "--topic=$incomingTopic")
Ensure-GCloudResource "Pub/Sub dead-letter subscription $deadLetterSubscription" @("pubsub", "subscriptions", "describe", $deadLetterSubscription) @("pubsub", "subscriptions", "create", $deadLetterSubscription, "--topic=$deadLetterTopic")

Ensure-GCloudResource "service account $serviceAccountEmail" @("iam", "service-accounts", "describe", $serviceAccountEmail) @("iam", "service-accounts", "create", $ServiceAccount, "--display-name=SentinelOps Cloud Run runtime")
Invoke-GCloud @("projects", "add-iam-policy-binding", $ProjectId, "--member=serviceAccount:$serviceAccountEmail", "--role=roles/datastore.user")
Invoke-GCloud @("projects", "add-iam-policy-binding", $ProjectId, "--member=serviceAccount:$serviceAccountEmail", "--role=roles/pubsub.publisher")
Invoke-GCloud @("projects", "add-iam-policy-binding", $ProjectId, "--member=serviceAccount:$serviceAccountEmail", "--role=roles/pubsub.subscriber")

if ($CreateSecret) {
    Ensure-GCloudResource "Secret Manager secret $SecretName" @("secrets", "describe", $SecretName) @("secrets", "create", $SecretName, "--replication-policy=automatic")
    Invoke-GCloud @("projects", "add-iam-policy-binding", $ProjectId, "--member=serviceAccount:$serviceAccountEmail", "--role=roles/secretmanager.secretAccessor")
    Write-Host "After bootstrap, add the key interactively with: gcloud secrets versions add $SecretName --data-file=-" -ForegroundColor Yellow
}

Write-Host "Cloud Run deployment command:" -ForegroundColor Green
Write-Host ".\scripts\deploy-cloudrun.ps1 -ProjectId $ProjectId -Region $Region -Mode gemini -Store firestore -EnablePubSub -UseSecretManager -GeminiSecret $SecretName"
