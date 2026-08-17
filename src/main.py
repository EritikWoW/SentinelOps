from fastapi import FastAPI

from src.models.incident import IncidentCreate, IncidentResponse

app = FastAPI(title="SentinelOps", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinelops"}


@app.post("/incidents", response_model=IncidentResponse, status_code=202)
def create_incident(payload: IncidentCreate) -> IncidentResponse:
    return IncidentResponse.accepted(payload)
