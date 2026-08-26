# WebMCP deployment

SentinelOps deploys to the existing Cloud Run service:

- Project: `sentinelops-505805`
- Region: `europe-west1`
- Service: `sentinelops`

The repository includes a manual GitHub Actions workflow at `.github/workflows/deploy-cloud-run.yml`.

## Authentication

The deployment workflow uses GitHub OIDC with Google Cloud Workload Identity Federation. It does not require a downloaded service-account key.

The production GitHub environment must provide these secrets:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

The service account must have the minimum roles required to build from source and update the existing Cloud Run service. Keep permissions scoped to the SentinelOps project and deployment target.

## Deployment safety

The workflow verifies the fixed project, region, and Cloud Run service before deploying. It deploys the checked-out commit and then calls the live `/health` endpoint. A failed health request fails the workflow.

WebMCP remains a browser-side progressive enhancement. Deploying the WebMCP bridge does not replace the existing SentinelOps backend incident workflow or its approval, remediation, and verification gates.

## Run

Use GitHub Actions -> `Deploy SentinelOps to Cloud Run` -> `Run workflow` from `main` after the deployment workflow has been merged and the two production secrets are configured.
