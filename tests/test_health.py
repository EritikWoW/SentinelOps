from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "sentinelops"}


def test_create_incident() -> None:
    response = client.post(
        "/incidents",
        json={
            "service": "demo-api",
            "severity": "high",
            "summary": "HTTP 500 rate exceeded threshold",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["service"] == "demo-api"
    assert body["incident_id"].startswith("inc_")
