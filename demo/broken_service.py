"""Cloud Run demo target with deterministic healthy and broken revisions."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sentinelops-demo-api")

app = FastAPI(title="SentinelOps Demo API")
VERSION = os.getenv("DEMO_VERSION", "v1").strip() or "v1"
BROKEN = os.getenv("DEMO_BROKEN", "false").strip().lower() == "true"
FAILURE_REASON = os.getenv("DEMO_FAILURE_REASON", "database connection failed").strip()


@app.get("/health")
def health() -> JSONResponse:
    if BROKEN:
        logger.error(
            "demo_api_health_failed version=%s reason=%s",
            VERSION,
            FAILURE_REASON,
        )
        return JSONResponse(
            status_code=500,
            content={
                "service": "demo-api",
                "version": VERSION,
                "status": "unhealthy",
                "reason": FAILURE_REASON,
            },
        )

    logger.info("demo_api_health_ok version=%s", VERSION)
    return JSONResponse(
        status_code=200,
        content={"service": "demo-api", "version": VERSION, "status": "healthy"},
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "demo-api",
        "version": VERSION,
        "status": "broken" if BROKEN else "healthy",
    }


@app.get("/work")
def work() -> JSONResponse:
    """Return a realistic application response used to generate 5xx traffic."""

    if BROKEN:
        logger.error("demo_api_request_failed version=%s reason=%s", VERSION, FAILURE_REASON)
        return JSONResponse(
            status_code=500,
            content={"error": "internal server error", "version": VERSION},
        )
    return JSONResponse(status_code=200, content={"result": "ok", "version": VERSION})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
