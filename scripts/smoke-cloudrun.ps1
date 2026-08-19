param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")
$health = Invoke-RestMethod -Uri "$base/health"
if ($health.status -ne "ok") { throw "Health check failed" }
$ready = Invoke-RestMethod -Uri "$base/ready"
if ($ready.status -ne "ready") { throw "Readiness check failed" }

$heartbeat = @{ node_id = "smoke-node"; hostname = "cloud-smoke"; platform = "cloud-run"; version = "0.3.0"; services = @("demo-api") } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/nodes/heartbeat" -Method Post -ContentType "application/json" -Body $heartbeat | Out-Null
$event = @{ node_id = "smoke-node"; hostname = "cloud-smoke"; service = "demo-api"; severity = "high"; source = "manual"; trigger = "cloud_smoke"; message = "Cloud Run event path smoke test"; evidence = @() } | ConvertTo-Json -Depth 5
$ingested = Invoke-RestMethod -Uri "$base/events" -Method Post -ContentType "application/json" -Body $event
if (-not $ingested.incident.incident_id) { throw "Event ingestion failed" }
$node = Invoke-RestMethod -Uri "$base/nodes/smoke-node"
if ($node.active_incidents -lt 1) { throw "Node active incident counter did not increment" }

$body = @{
    service = "demo-api"
    severity = "high"
    summary = "HTTP 500 rate exceeded after latest deployment"
} | ConvertTo-Json
$incident = Invoke-RestMethod -Uri "$base/incidents" -Method Post -ContentType "application/json" -Body $body
if ($incident.approval_status -ne "pending") { throw "Expected pending approval" }

$approval = @{ decision = "approve"; comment = "Approved for Cloud Run demo" } | ConvertTo-Json
$approved = Invoke-RestMethod -Uri "$base/incidents/$($incident.incident_id)/approval" -Method Post -ContentType "application/json" -Body $approval
$executed = Invoke-RestMethod -Uri "$base/incidents/$($incident.incident_id)/execute" -Method Post -ContentType "application/json" -Body '{"confirm":true}'
if ($executed.analysis.remediation_status -ne "executed") { throw "Expected executed remediation" }
$verified = Invoke-RestMethod -Uri "$base/incidents/$($incident.incident_id)/verify" -Method Post -ContentType "application/json" -Body '{"passed":true,"notes":"Cloud Run demo health checks passed."}'
if ($verified.analysis.verification_status -ne "passed") { throw "Expected passed verification" }

[pscustomobject]@{
    service = $executed.service
    incident_id = $executed.incident_id
    approval_status = $approved.approval_status
    remediation_status = $executed.analysis.remediation_status
    verification_status = $verified.analysis.verification_status
    execution_mode = $executed.execution_mode
    node_active_incidents = $node.active_incidents
}
