# SentinelOps Development Plan

This file is the implementation contract for the SentinelOps hackathon build.
Work proceeds in phase order. Existing API routes, dashboard behavior,
approval boundaries, storage adapters, demo mode, and Google ADK integration
remain backward compatible unless a change is recorded here.

## Current baseline

- Control Plane: FastAPI, Google ADK/Gemini coordinator, incident lifecycle,
  approval flow, memory/JSON/Firestore stores, local event publisher, dashboard.
- Dashboard: incidents, history search/filtering, event payload inspection,
  Workflow observability, Safety Policy, Settings, fixed viewport layout.
- Safety: demo remediation changes only local incident state; no production
  infrastructure mutation is claimed.
- Verification baseline: existing test suite passes before each phase transition.

## Phase 1 — SentinelOps Node, collectors, and event ingestion

Status: `completed`

### Deliverables

- `src/models/evidence.py`: structured `EvidenceItem` with compatibility for
  existing string evidence.
- `src/models/events.py`: normalized external event and node heartbeat models.
- `src/node/__init__.py`, `src/node/config.py`, `src/node/models.py`,
  `src/node/agent.py`: lightweight configurable Node process and CLI.
- `src/collectors/base.py`: collector protocol and normalized collector result.
- `src/collectors/log_file.py`: tail-style file reader with offset, append-only
  reads, truncation/rotation handling, rules, and bounded context collection.
- `src/collectors/healthcheck.py`: HTTP checks with timeout, consecutive-failure
  threshold, and recovery detection.
- `src/collectors/process.py`: portable process-state interface with safe local
  implementation and extension points for Windows Services/systemd/Docker.
- `src/services/ingestion.py`: conversion from normalized events to incidents.
- `src/services/node_registry.py`: heartbeat, last-seen, online/offline status.
- `POST /events`: ingest normalized external events without replacing existing
  `GET /events` or event replay.
- `POST /nodes/heartbeat`, `GET /nodes`, and `GET /nodes/{node_id}`.
- Separate `node.yaml` configuration and `python -m src.node.agent --config ...`.

### Acceptance checks

- A matching log rule creates one normalized event, not one Gemini request per
  log line.
- INFO lines without a matching rule do not create incidents.
- A healthcheck creates an incident only after its configured failure threshold.
- A recovery emits a recovery event.
- A Node heartbeat is visible as online and becomes offline after stale timeout.
- Old `POST /incidents` payloads continue to work unchanged.

## Phase 2 — Typed tools and safety policy

Status: `completed`

### Deliverables

- `src/tools/logs.py`: `get_recent_logs(...)`.
- `src/tools/health.py`: `get_health_status(...)`.
- `src/tools/process.py`: `get_process_status(...)`.
- `src/tools/remediation.py`: typed remediation results and adapter boundary.
- `src/policy/safety.py`: allowlist, risk classification, and approval policy.
- ADK tool wiring restricted to typed tools; no arbitrary shell execution.
- Gemini prompts grounded only in supplied incident evidence and tool results.

### Acceptance checks

- Read-only tools are allowed automatically.
- High-impact actions require approval.
- Destructive actions are blocked unless explicitly supported by policy.
- Unsupported tools return `supported: false`, `executed: false`, and a reason.
- No tool reports success without a real execution result.

## Phase 3 — Remediation adapters and verification loop

Status: `completed`

### Deliverables

- `src/tools/adapters/process_adapter.py`.
- `src/tools/adapters/service_adapter.py`.
- `src/services/verification.py`.
- Explicit remediation states: requested, awaiting approval, unsupported,
  verification pending, resolved, and remediation failed.
- Health verification after every supported remediation.

### Acceptance checks

- A proposal never marks an incident resolved.
- Unsupported process/service actions remain visibly unsupported.
- Healthy post-action checks produce `resolved`.
- Failed post-action checks produce `remediation_failed` or remain investigating.

## Phase 4 — Pub/Sub inbound consumer and cloud persistence

Status: `completed`

### Deliverables

- Explicit `EventPublisher` and `EventConsumer` interfaces.
- Pub/Sub inbound subscriber adapter without claiming bidirectional support
  before it is configured.
- Firestore persistence for incidents, evidence, nodes, and event history.
- Cloud deployment configuration for the Node/event contracts.

### Acceptance checks

- Existing local event publisher remains usable offline.
- External alert adapters map into the same normalized event model.
- Firestore mode preserves incident lifecycle and node status.
- Secrets remain outside source control and logs.

## Phase 5 — Demo environment, UI support, tests, and documentation

Status: `completed`

### Deliverables

- `demo/broken_service.py`.
- `demo/generate_errors.py`.
- Reproducible `node.yaml` demo configuration.
- UI Nodes data endpoint integration when the backend contract is stable.
- README update with Control Plane/Node split, Mermaid architecture,
  implemented versus planned features, and exact demo commands.
- `docs/node.md` and `docs/tools-and-safety.md`.

### Acceptance checks

- API, Node, and demo service run in separate terminals.
- Breaking the demo service creates an incident without manual `POST /incidents`.
- Incident contains real log/health evidence.
- Analysis, approval, remediation, and verification are observable in UI.
- Only successful verification reaches resolved state.
- Full unit/integration suite passes.

## Cross-phase rules

- Do not send an entire log stream to Gemini; detectors trigger bounded evidence
  collection first.
- Do not let Gemini execute shell commands directly.
- Do not add platform-specific logic to the coordinator.
- Do not use fake success for unsupported remediation.
- Do not remove or rename existing public endpoints without compatibility.
- Do not log API keys, tokens, or `.env` contents.
- Do not advance a phase until its acceptance checks and tests pass.

## Phase 6 — Operator-ready Node operations

Status: `completed`

### Deliverables

- Make the existing Node environment card open a live Nodes panel with
  heartbeat age, platform, monitored services, and active incident count.
- Track active incidents per Node and remove them after successful verification.
- Use the healthcheck evidence URL for the dashboard verification action when
  available; retain the old manual verification endpoint as fallback.
- Keep the dashboard fixed-layout and preserve the reference visual language.

### Acceptance checks

- A heartbeat appears in the Nodes panel as online.
- A Node-created incident increments its active incident count.
- Successful health verification returns the incident to a resolved state and
  decrements the active count.
- Manual incidents without health evidence keep the existing verification flow.
- UI browser flow and full test suite pass.

## Change log

- 2026-08-17: Plan established from the SentinelOps hackathon implementation
  brief. Phase 1 is the active implementation target.
- 2026-08-17: Added structured evidence/events, Node heartbeat and ingestion
  endpoints, log/health/process collectors, YAML Node configuration, and the
  standalone Node process. Phase 1 acceptance checks passed.
- 2026-08-17: Completed typed read-only tools, ADK tool wiring, Safety Policy,
  unsupported remediation adapters, and health-based verification. Phase 4 is
  the next active implementation target.
- 2026-08-17: Separated EventConsumer from EventPublisher, added inbound
  Pub/Sub subscription adapter, and added Firestore-backed Node and event
  history persistence. Phase 5 is now the active implementation target.
- 2026-08-17: Verified the local broken-service flow end-to-end: Node heartbeat,
  log trigger, health failure threshold, normalized ingestion, and structured
  evidence all reached the Control Plane without manual incident creation.
- 2026-08-17: Connected the dashboard environment card to the Node registry so
  online heartbeat state is visible in the existing UI.
- 2026-08-17: Completed the reproducible broken-service demo, Node documentation,
  UI Node status, and full Phase 5 test/verification pass.
- 2026-08-17: Phase 6 started to connect Node operations and evidence-aware
  verification to the operator UI.
- 2026-08-17: Completed Phase 6: live Nodes panel, per-Node active incident
  counters, automatic health-evidence verification, keyboard-accessible Node
  card, and 17-test plus fixed-viewport browser verification pass.

## Phase 7 — Cloud Run packaging and production configuration

Status: `completed`

### Deliverables

- Dependency-free `/ready` endpoint for Cloud Run readiness checks.
- Non-root production container with a minimal build context.
- Deployment script with explicit demo/Gemini modes, memory store or Firestore,
  bounded Cloud Run scaling, and optional Secret Manager API-key injection.
- Local validation script that checks deployment files, container safety, Python
  compilation, and secret exclusions without requiring Docker or gcloud.

### Acceptance checks

- `/health` and `/ready` return safe responses without credentials.
- Container configuration runs as non-root and excludes `.env`, tests, and
  development artifacts from the build context.
- Gemini Cloud Run deployment refuses to proceed unless Secret Manager is used.
- Demo Cloud Run deployment remains keyless and starts in simulation-only mode.
- Local cloud configuration validation and full test suite pass.

### Phase 7 result

- `/ready` returns a credential-free readiness payload.
- Cloud configuration validation passed without Docker or gcloud installed.
- Gemini deployment is blocked before cloud commands unless Secret Manager is
  explicitly selected.
- Demo deployment remains keyless and simulation-only.

## Change log (continued)

- 2026-08-17: Completed Phase 7: readiness endpoint, non-root Cloud Run image,
  minimal build context, Secret Manager guard, and local cloud configuration
  validation. Full suite reached 18 passing tests.

## Phase 8 — Cloud event configuration completeness

Status: `completed`

### Deliverables

- Expose the inbound Pub/Sub subscription as a first-class safe setting.
- Persist `PUBSUB_SUBSCRIPTION` without touching credentials.
- Keep outbound topic and inbound subscription independently configurable.
- Document the full cloud event configuration contract.

### Acceptance checks

- Settings API returns the subscription name without secrets.
- Settings UI can save and reload topic plus subscription.
- `.env.example` contains the complete Pub/Sub configuration surface.
- Existing local demo remains unchanged when subscription is empty.
- Full test suite and JavaScript validation pass.

### Phase 8 result

- Pub/Sub topic/subscription settings are now wired end-to-end through API,
  dashboard, `.env`, and runtime consumers.

## Phase 9 — Google Cloud resource bootstrap

Status: `completed`

### Deliverables

- Idempotent-style bootstrap command contract for required Google APIs,
  Firestore, Pub/Sub topic/subscription, runtime service account, IAM roles,
  and optional Secret Manager secret.
- Explicit plan/apply boundary so cloud mutations never happen accidentally.
- Dedicated validation coverage for the bootstrap script and its secret-safe
  deployment handoff.

### Acceptance checks

- Plan mode prints intended commands without changing cloud state.
- Apply mode is impossible to reach without explicit `-Apply`.
- Runtime service account receives only datastore, Pub/Sub, and optional secret
  accessor roles.
- Gemini key is entered separately through Secret Manager and never appears in
  source files or command arguments.
- Local validation and full test suite pass without gcloud installed.

### Phase 9 result

- Added `scripts/bootstrap-gcp.ps1` and documented the safe plan/apply flow.
- The local machine has no `gcloud` executable, so no external cloud mutation
  was attempted.

## Phase 10 — Cloud Run runtime lifecycle and smoke path

Status: `completed`

### Deliverables

- Start and stop the optional Pub/Sub consumer with the FastAPI application
  lifecycle.
- Route inbound Pub/Sub payloads through the same normalized event contract as
  `POST /events`.
- Deploy Cloud Run with the dedicated runtime service account and optional
  Pub/Sub subscription flag.
- Extend cloud smoke testing to readiness, heartbeat, event ingestion, and the
  per-Node active incident counter.

### Acceptance checks

- Consumer start/stop is tied to application lifespan.
- Inbound payloads cannot bypass Pydantic event validation.
- Cloud Run deployment selects the dedicated service account.
- Smoke script validates `/ready`, Node heartbeat, event ingestion, and the
  existing approval/remediation/verification flow.
- Full tests and local cloud validation pass without gcloud.

### Phase 10 result

- Runtime lifecycle and smoke path are implemented and covered by tests.
- Real Pub/Sub/Cloud Run execution remains intentionally deferred until the
  Google Cloud CLI and project permissions are available.

## Phase 11 — Repeatable cloud bootstrap

Status: `completed`

### Deliverables

- Resource existence checks for Firestore, Pub/Sub, service account, and
  Secret Manager before create operations.
- Safe rerun behavior that skips already-provisioned resources and still
  reapplies IAM bindings.
- Local validation that enforces the repeatable bootstrap contract.

### Acceptance checks

- Plan mode remains side-effect free and prints the intended creates.
- Apply mode queries each resource before creating it.
- Existing resources are skipped instead of causing a failed bootstrap.
- IAM bindings remain safe to reapply.
- Cloud validation and full test suite pass without gcloud installed.

### Phase 11 result

- `bootstrap-gcp.ps1` is now safe to rerun after an interrupted or partially
  completed setup.

## Phase 12 — Cloud Run post-deploy verification

Status: `completed`

### Deliverables

- Read-only `verify-cloudrun.ps1` operational check.
- Verification of Cloud Run service account and public service URL.
- Verification of `/health`, `/ready`, safe settings, and Gemini-mode secret
  presence without exposing secret material.

### Acceptance checks

- Verification performs no resource mutations.
- Gemini mode fails verification when the runtime has no configured key.
- Demo mode can be verified without a key.
- Cloud configuration validation and full test suite pass locally.

### Phase 12 result

- Added the post-deploy verification command and documented it beside the
  deployment and smoke commands.
- Local mode still uses the in-memory bus unless Pub/Sub is explicitly enabled.
