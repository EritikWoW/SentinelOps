# SentinelOps

Autonomous AI incident commander for detecting, investigating, remediating, and verifying service incidents.

SentinelOps is being built for the **All Things Agentic Hackathon** in the **Taskmaster** category. The project uses Google Agent Development Kit (ADK), Gemini, and Google Cloud to run an event-driven incident-response workflow that takes action instead of only producing recommendations.

## Core workflow

`Detect -> Investigate -> Decide -> Remediate -> Verify -> Report`

A typical demo scenario is a faulty deployment that causes elevated HTTP 500 errors. SentinelOps receives the incident event, gathers logs and deployment context, correlates the failure with recent code changes, selects a safe remediation action, verifies recovery, and produces an incident timeline.

## Planned architecture

- **FastAPI / Cloud Run** - incident webhook and API surface
- **Pub/Sub** - event ingestion and fan-out
- **Google ADK** - coordinator and specialized agents
- **Gemini 3.5 Flash** - reasoning, correlation, summarization, and decision support
- **Cloud Logging** - operational evidence
- **Firestore** - incident state, execution history, and memory
- **GitHub API** - commit, diff, repository, and pull-request context

Specialized agents:

- Incident Coordinator
- Log Analysis Agent
- Infrastructure Agent
- Code Analysis Agent
- Remediation Agent
- Verification Agent

## Safety model

SentinelOps uses permission-scoped tools and risk-aware action policies.

Low-risk operations such as reading logs, analyzing metrics, and running health checks can be autonomous. High-impact or destructive actions must be blocked or require explicit human approval.

## Repository status

This repository is an active hackathon build. The current scaffold establishes the API, agent boundaries, configuration, Docker runtime, and reproducible setup instructions. Google Cloud integrations will be wired in incrementally as the MVP is implemented.

## Requirements

- Python 3.11+
- Docker (optional, recommended for reproducibility)
- A Gemini API key or Vertex AI configuration
- Google Cloud project for Cloud Run / Pub/Sub / Firestore integration

## Local setup

### 1. Clone the repository

```bash
git clone https://github.com/EritikWoW/SentinelOps.git
cd SentinelOps
```

### 2. Create a virtual environment

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

On Windows:

```powershell
Copy-Item .env.example .env
```

Set at minimum:

```env
GEMINI_API_KEY=your_key_here
```

### 5. Run the API

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

Then verify:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"ok","service":"sentinelops"}
```

## Docker reproducible test

Build:

```bash
docker build -t sentinelops .
```

Run:

```bash
docker run --rm -p 8080:8080 --env-file .env sentinelops
```

Verify:

```bash
curl http://localhost:8080/health
```

## Incident API smoke test

Start the API, then send a synthetic incident:

```bash
curl -X POST http://localhost:8080/incidents \
  -H "Content-Type: application/json" \
  -d '{"service":"demo-api","severity":"high","summary":"HTTP 500 rate exceeded threshold"}'
```

The endpoint currently returns a deterministic scaffold response. The ADK coordinator will replace this stub as implementation progresses.

## Cloud Run deployment

Once the Google Cloud project is configured:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy sentinelops --source . --region europe-west1
```

After deployment, record the generated `.run.app` URL for the Devpost hosted-project field and capture the Cloud Run dashboard/logs for the demo video.

## Reproducible testing checklist

A judge or reviewer should be able to validate the current scaffold with:

```bash
git clone https://github.com/EritikWoW/SentinelOps.git
cd SentinelOps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --host 0.0.0.0 --port 8080
curl http://localhost:8080/health
```

Expected result: HTTP 200 with the SentinelOps health payload.

For the incident endpoint, use the smoke-test request shown above and verify that the API returns an accepted incident object and a generated incident id.

## Project structure

```text
SentinelOps/
├── README.md
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
├── docs/
│   └── architecture.md
├── src/
│   ├── main.py
│   ├── agents/
│   │   ├── coordinator.py
│   │   ├── log_agent.py
│   │   ├── infrastructure_agent.py
│   │   ├── code_agent.py
│   │   ├── remediation_agent.py
│   │   └── verification_agent.py
│   └── models/
│       └── incident.py
└── tests/
    └── test_health.py
```

## Hackathon deliverables

- Working Gemini + ADK agent workflow
- Google Cloud deployment
- Public source repository
- Reproducible README instructions
- Architecture diagram
- Approximately 4-minute demo video
- Live incident -> analysis -> remediation -> verification scenario
