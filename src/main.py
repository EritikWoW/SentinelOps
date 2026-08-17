import json

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from src.agents.coordinator import IncidentCoordinator
from src.models.incident import IncidentAnalysis, IncidentCreate, IncidentResponse

app = FastAPI(title="SentinelOps", version="0.2.0")
coordinator = IncidentCoordinator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinelops"}


@app.post("/incidents", response_model=IncidentResponse, status_code=202)
def create_incident(payload: IncidentCreate) -> IncidentResponse:
    """Analyze a newly received incident with Gemini.

    This is the first live reasoning path of the MVP. Execution tools and
    verification loops will be connected after the reasoning contract is stable.
    """

    try:
        raw_analysis = coordinator.analyze(payload)
        parsed = json.loads(raw_analysis)
        analysis = IncidentAnalysis.model_validate(parsed)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid Gemini analysis response: {exc}",
        ) from exc

    return IncidentResponse.analyzed(payload, analysis)
