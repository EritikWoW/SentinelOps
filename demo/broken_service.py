"""Small service whose health and log state can be broken and recovered."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn


LOG_PATH = Path(__file__).parent / "logs" / "application.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("sentinelops-demo")
app = FastAPI(title="SentinelOps Demo Service")
broken = False


@app.get("/health")
def health() -> JSONResponse:
    if broken:
        logger.error("FATAL database connection failed; demo service is broken")
        return JSONResponse(status_code=500, content={"status": "unhealthy", "reason": "database connection failed"})
    return JSONResponse(status_code=200, content={"status": "healthy"})


@app.post("/break")
def break_service() -> dict[str, str]:
    global broken
    broken = True
    logger.error("FATAL database connection failed; demo service entered broken state")
    return {"status": "broken"}


@app.post("/recover")
def recover_service() -> dict[str, str]:
    global broken
    broken = False
    logger.info("INFO database connection restored; demo service recovered")
    return {"status": "healthy"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "demo-api", "status": "broken" if broken else "healthy"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SentinelOps broken service demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
