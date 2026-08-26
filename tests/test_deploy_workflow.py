from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-cloud-run.yml"


def test_deploy_workflow_targets_existing_sentinelops_service() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "GCP_PROJECT_ID: sentinelops-505805" in text
    assert "GCP_REGION: europe-west1" in text
    assert "CLOUD_RUN_SERVICE: sentinelops" in text


def test_deploy_workflow_uses_oidc_not_static_key() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "workload_identity_provider:" in text
    assert "service_account:" in text
    assert "credentials_json" not in text
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in text


def test_deploy_workflow_verifies_health_after_deploy() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "gcloud run deploy" in text
    assert 'curl --fail --silent --show-error "${SERVICE_URL}/health"' in text
