# SentinelOps

**Autonomous AI incident commander for closed-loop production recovery.**

SentinelOps is built for the **All Things Agentic Hackathon** in the **Taskmaster** category. It uses **Gemini 3.5 Flash**, **Google Agent Development Kit (ADK)**, and **Google Cloud** to detect incidents, investigate them, choose a remediation path, pause for human approval when the action is high-risk, execute a real remediation, verify recovery, and produce a final incident report.

> An incident is not resolved when the agent proposes a solution. It is resolved when the system proves that the service is healthy again.

**Hosted control plane:** `https://sentinelops-761693711271.europe-west1.run.app/`

## Why this is a Taskmaster agent

The Taskmaster track focuses on event-driven workflows with autonomous routing: the system should notice a change, decide what happens next, interact with services, and complete a multi-step task without the user guiding every step.

SentinelOps follows exactly that pattern:

`Detect -> Investigate -> Decide -> Remediate -> Verify -> Report`

A Cloud Run failure can trigger the workflow automatically through Cloud Logging and Pub/Sub. The user does not manually walk the agent through investigation steps. The agent gathers evidence, reasons about the failure, proposes the next action, and continues the lifecycle until recovery is proven.

Human approval is intentionally retained for high-impact infrastructure mutation. This is a safety boundary, not the primary orchestration mechanism.

## Problem

Production incident response is still heavily manual. An engineer often has to:

1. notice an alert;
2. identify the affected service and revision;
3. inspect logs and runtime context;
4. decide whether a rollback is appropriate;
5. execute the rollback;
6. verify that the service actually recovered;
7. document what happened.

The expensive part is not generating a recommendation. It is coordinating evidence, decisions, action, verification, and reporting safely under time pressure.

SentinelOps automates that operational loop.

## Value proposition

SentinelOps reduces incident-response friction by turning an operational signal into a persisted, observable workflow instead of another chat conversation.

The agent can autonomously perform low-risk investigation and reasoning, while dangerous changes remain behind explicit policy checks and human approval. After approval, remediation is executed through a typed allowlisted tool, and the incident cannot be marked resolved until a real health check succeeds.

This creates a useful separation:

- **autonomous where safe** — detection, evidence gathering, analysis, correlation, planning;
- **human-authorized where risky** — production-changing remediation;
- **machine-verified after action** — recovery must be proven, not assumed.

## What is implemented

- **Automatic Cloud Run failure detection** from HTTP 5xx request logs through Cloud Logging Log Router.
- **Authenticated Pub/Sub push ingestion** into the SentinelOps control plane.
- **Incident correlation** to suppress repeated detector events during the same incident window.
- **Google ADK + Gemini investigation** with an Incident Commander and specialist agents.
- **Bounded read-only tools** for gathering operational evidence.
- **Structured incident analysis** with evidence, root-cause hypothesis, risk, remediation plan, and verification plan.
- **Human approval gate** for high-impact remediation.
- **Allowlisted live Cloud Run rollback** to an explicit target revision and region.
- **Real health verification** before resolution.
- **Deterministic final report stage** after verification.
- **Firestore persistence** for incident lifecycle state.
- **Pub/Sub workflow events** for control-plane observability.
- **Live dashboard** for incidents, workflow state, approval, execution, verification, runtime state, and Node state.
- **SentinelOps Node** for local log, health, process, heartbeat, and normalized-event collection.
- **Safe local demo mode** for deterministic development without mutating cloud infrastructure.

## Live architecture

```mermaid
flowchart LR
  User[Real HTTP request] --> Service[Cloud Run service]
  Service -->|HTTP 5xx| Logging[Cloud Logging]
  Logging --> Router[Log Router sink]
  Router --> Topic[Pub/Sub incoming topic]
  Topic -->|Authenticated push| API[SentinelOps Cloud Run]

  API --> Correlate[Incident correlation]
  Correlate --> ADK[ADK Incident Commander]
  ADK --> Gemini[Gemini 3.5 Flash]
  ADK --> Tools[Read-only evidence tools]

  Gemini --> Decision[Structured incident analysis]
  Decision --> Gate{Safety policy}
  Gate -->|High risk| Approval[Human approval]
  Approval --> Executor[Allowlisted Cloud Run rollback]
  Executor --> Service
  Service --> Verify[Real health verification]
  Verify --> Report[Final incident report]

  API --> Firestore[(Firestore)]
  API --> Events[Pub/Sub workflow events]
```

The same architecture is documented in more detail in [`docs/architecture.md`](docs/architecture.md).

## Agent architecture

The ADK control plane uses an Incident Commander plus specialist agents for:

- log analysis;
- infrastructure context;
- code and deployment context;
- remediation planning;
- verification planning.

The commander performs investigation with tools first. A separate formatter agent then converts the investigation result into the structured `IncidentAnalysis` contract. This avoids coupling tool/function-call output to the final response schema.

## Safety model

SentinelOps does not give Gemini unrestricted infrastructure access.

Read-only inspection can run autonomously. High-impact remediation remains behind explicit policy checks and human approval. Live Cloud Run rollback is additionally constrained by:

- `SENTINELOPS_REMEDIATION_ALLOWED_SERVICES`;
- an explicit target revision;
- revision/service ownership validation;
- an explicit execution confirmation;
- typed Cloud Run remediation code rather than arbitrary shell execution;
- real post-remediation health verification.

A blocked, rejected, failed, or unverified action cannot be represented as a successfully resolved incident.

## Real closed-loop demo flow

The primary demo target is `demo-api`, deployed as separate healthy and broken Cloud Run revisions.

1. A broken revision receives production traffic.
2. `/health` or `/work` returns a real HTTP 500 response.
3. Cloud Run writes the request failure into Cloud Logging.
4. A Log Router sink exports matching 5xx request logs to Pub/Sub.
5. Pub/Sub pushes the event to SentinelOps.
6. SentinelOps correlates repeated signals and creates one incident.
7. Google ADK + Gemini investigate the failure and propose remediation.
8. The workflow pauses if human approval is required.
9. After approval, SentinelOps routes 100% of Cloud Run traffic to the known healthy revision.
10. SentinelOps performs a real HTTP health verification.
11. Only after HTTP 200 recovery does the workflow complete `Verify` and `Report` and mark the incident `resolved`.

This demonstrates a real event, a real agent decision, a real infrastructure action, and real proof of recovery.

## Technologies used

### Google AI and agent framework

- **Gemini 3.5 Flash** through Vertex AI
- **Google Agent Development Kit (ADK)**
- Vertex AI Application Default Credentials from the Cloud Run service identity

### Google Cloud

- **Cloud Run** — SentinelOps control plane and remediation target
- **Cloud Logging / Log Router** — operational failure signal
- **Pub/Sub** — event-driven ingestion and workflow events
- **Firestore** — incident and runtime state persistence
- **Cloud Run Admin API** — allowlisted traffic rollback

### Application stack

- Python 3.11+
- FastAPI
- Docker
- GitHub API integration
- HTML/CSS/JavaScript live dashboard

## Data sources and operational evidence

SentinelOps can work with bounded operational evidence rather than sending an unrestricted stream of logs to the model.

Current sources include:

- Cloud Run HTTP request logs;
- Cloud Logging entries routed through Pub/Sub;
- incident event payloads and normalized evidence;
- Cloud Run service/revision context;
- health endpoint responses;
- optional GitHub repository, commit, diff, and pull-request context;
- SentinelOps Node log, health, process, and heartbeat signals.

The design intentionally favors **trigger -> relevant evidence -> agent reasoning** over streaming every log line to Gemini.

## Findings and learnings

Several implementation lessons shaped the final architecture:

1. **A recommendation is not a remediation.** The workflow became materially more useful only after execution and verification were part of the same incident lifecycle.
2. **Tool use and structured output should be separated.** Running an investigation agent with tools and then formatting its result with a schema-only agent proved more reliable than combining function calls and final schema generation in one step.
3. **Request logs are stronger failure signals than application text logs.** Cloud Run request logs expose actual HTTP status metadata, which made automatic 5xx detection more reliable than matching free-form stderr text.
4. **High-risk autonomy needs explicit boundaries.** Approval, allowlists, explicit revision selection, ownership validation, and typed executors make autonomous investigation compatible with controlled production mutation.
5. **Verification must be first-class.** An incident should remain unresolved until the service itself proves recovery.
6. **Event-driven systems need idempotency and correlation.** Repeated 5xx signals can represent one incident, so detector events must be correlated rather than blindly creating new workflows.
7. **Persistent state matters.** Firestore keeps incident lifecycle state outside the process, which is necessary for a credible cloud control plane.

## Reproducible testing / spin-up instructions

These instructions are included specifically so judges and reviewers can reproduce the project locally or understand how the cloud deployment is assembled.

### 1. Clone the repository

```bash
git clone https://github.com/EritikWoW/SentinelOps.git
cd SentinelOps
```

### 2. Create a Python environment

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

### 4. Create local configuration

Linux / macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

The safe local defaults are:

```env
SENTINELOPS_MODE=demo
SENTINELOPS_STORE=memory
PUBSUB_ENABLED=false
```

### 5. Run the control plane locally

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

Verify the API:

```bash
curl http://localhost:8080/health
```

Expected:

```json
{"status":"ok","service":"sentinelops"}
```

Open the dashboard:

```text
http://127.0.0.1:8080/
```

### 6. Run automated tests

```bash
python -m pytest -q
```

CI also runs the automated test suite for pull requests.

### 7. Optional local incident smoke test

```bash
curl -X POST http://127.0.0.1:8080/incidents \
  -H "Content-Type: application/json" \
  -d '{"service":"demo-api","severity":"high","summary":"HTTP 500 rate exceeded threshold"}'
```

In local demo mode this exercises the same incident contract without performing production infrastructure mutation.

## Gemini / Vertex AI mode

Cloud Run uses Application Default Credentials through its service identity. No `GOOGLE_APPLICATION_CREDENTIALS` file is required inside the container.

Typical live configuration:

```env
SENTINELOPS_MODE=gemini
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-3.5-flash
SENTINELOPS_STORE=firestore
FIRESTORE_DATABASE=(default)
PUBSUB_ENABLED=true
PUBSUB_DELIVERY_MODE=push
PUBSUB_TOPIC=sentinelops-incoming-events
PUBSUB_INTERNAL_TOPIC=sentinelops-internal-events
SENTINELOPS_REMEDIATION_ALLOWED_SERVICES=demo-api
```

The Cloud Run runtime identity must have only the permissions required by the configured deployment, including Vertex AI access and the specific Cloud Run permissions required for the allowlisted remediation path.

## Deploy SentinelOps to Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud run deploy sentinelops \
  --source . \
  --region=europe-west1 \
  --allow-unauthenticated
```

After deployment, verify:

```bash
SERVICE_URL="$(gcloud run services describe sentinelops \
  --region=europe-west1 \
  --format='value(status.url)')"

curl "$SERVICE_URL/health"
```

The public dashboard and API are served by the same Cloud Run service.

## Configure the Cloud Logging detector

The included setup script configures a project-level Log Router sink that exports new Cloud Run request logs with HTTP 5xx responses for the target service.

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
bash scripts/setup-cloud-logging-detector.sh
```

The detector uses a request-log filter equivalent to:

```text
resource.type="cloud_run_revision"
AND resource.labels.service_name="demo-api"
AND httpRequest.status>=500
```

The setup also grants the sink writer identity Pub/Sub Publisher on the incoming topic.

## Deploy the test service

The repository contains `demo-api`, a deterministic Cloud Run target used to prove the real rollback path.

Healthy revision:

```bash
bash scripts/deploy-demo-api.sh healthy
```

Broken revision:

```bash
bash scripts/deploy-demo-api.sh broken
```

The broken revision returns HTTP 500 from `/health` and `/work`; the healthy revision returns HTTP 200.

## Incident lifecycle API

```text
POST /incidents                            manually create and analyze an incident
GET  /incidents?limit=25                   list recent incidents
GET  /incidents/{incident_id}              retrieve one incident
POST /incidents/{incident_id}/approval     approve or reject remediation
POST /incidents/{incident_id}/execute      execute approved allowlisted remediation
POST /incidents/{incident_id}/verify       record an explicit verification result
POST /incidents/{incident_id}/verify/health
                                          run real HTTP health verification
GET  /events                               inspect workflow events
POST /events                               ingest one normalized detector event
POST /events/{event_id}/replay             replay one recorded event
POST /nodes/heartbeat                      register a SentinelOps Node heartbeat
GET  /nodes                                list Node state
GET  /nodes/{node_id}                      inspect one Node
GET  /settings                             inspect safe runtime configuration
```

Mutating control-plane routes can be protected with `SENTINELOPS_AUTH_REQUIRED=true` and `SENTINELOPS_API_TOKEN`.

## Dashboard

The root URL serves a live control-plane dashboard rather than a static demo page. It reads live state from `/incidents`, `/settings`, and `/nodes` and exposes only actions supported by the backend.

The dashboard includes:

- active incident count;
- current workflow phase;
- safety/automation state;
- evidence and root-cause hypothesis;
- remediation plan;
- approval and rejection controls;
- explicit Cloud Run rollback target revision and region;
- execution confirmation;
- real health verification;
- final report state;
- live refresh status;
- Node state;
- runtime mode and environment state.

Production settings are presented as read-only because durable Cloud Run configuration is deployment-managed.

## SentinelOps Node

Start a local Node with:

```bash
python -m src.node.agent --config node.yaml
```

The Node can monitor local logs, health endpoints, process state, and heartbeats and send normalized bounded evidence to the central control plane. It does not stream every log line to Gemini.

See [`docs/node.md`](docs/node.md) for the reproducible Node demo.

## Project structure

```text
SentinelOps/
├── demo/                       # healthy/broken Cloud Run test target
├── docs/                       # architecture and implementation notes
├── scripts/                    # cloud/bootstrap/detector/demo helpers
├── src/
│   ├── agents/                 # ADK commander and specialist agents
│   ├── models/                 # incident/event/settings contracts
│   ├── node/                   # SentinelOps Node
│   ├── policy/                 # safety policy
│   ├── services/               # stores, Pub/Sub, Cloud Run executor, verification
│   ├── web/                    # live dashboard
│   └── main.py                 # FastAPI control plane
└── tests/
```

## Hackathon requirement mapping

| Requirement | SentinelOps implementation |
|---|---|
| Gemini 3.5 or newer | Gemini 3.5 Flash through Vertex AI |
| Google Agent Framework | Google Agent Development Kit (ADK) |
| Google Cloud infrastructure | Cloud Run, Firestore, Pub/Sub, Cloud Logging |
| Autonomous workflow beyond chat | Event-driven incident lifecycle from detection through report |
| Taskmaster action | Real allowlisted Cloud Run rollback |
| Background/asynchronous operation | Cloud Logging -> Pub/Sub -> SentinelOps ingestion |
| Persistent state | Firestore incident lifecycle state |
| Architecture diagram | Mermaid diagram above + `docs/architecture.md` |
| Reproducible README | Local setup, tests, Cloud Run deployment, detector setup, demo service deployment |
| Hosted project | Public Cloud Run control plane URL listed at the top of this README |
| Google Cloud proof | Cloud Run deployment, Logging/Pub/Sub path, Vertex AI runtime, Firestore persistence |

## Judging criteria proof points

### Innovation & Operational Utility

SentinelOps removes a real multi-step operational chore. It does not stop at diagnosis: it coordinates detection, investigation, approval, remediation, verification, and reporting.

### Architectural Discipline & Tech Stack

The system separates event ingestion, state persistence, agent reasoning, policy, execution, and verification. Credentials use Cloud Run service identity / ADC rather than static key files. Remediation is allowlisted and typed. Incident state is persisted outside the process.

### Demo & Production Readiness

The repository includes reproducible setup instructions, automated tests, a live Cloud Run deployment path, a clear architecture diagram, a real Cloud Logging -> Pub/Sub detector, a real remediation executor, and real verification before resolution.

## Hackathon proof points

- **Real failure** — an actual Cloud Run revision returns HTTP 500.
- **Real event** — Cloud Logging and Pub/Sub create the incident automatically.
- **Real agent** — Google ADK + Gemini investigate the failure.
- **Real safety gate** — high-risk remediation stops for human approval.
- **Real action** — SentinelOps changes Cloud Run traffic to the approved healthy revision.
- **Real verification** — the service must return HTTP 200 before resolution.
- **Real report** — the completed workflow records a final incident report.

That closed loop is the core of SentinelOps.
