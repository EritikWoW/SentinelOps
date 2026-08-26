# SentinelOps — WebMCP Challenge Extension

SentinelOps existed before the WebMCP Challenge submission period. This document explicitly separates the pre-existing SentinelOps system from the WebMCP work added for the challenge.

## Pre-existing SentinelOps functionality

The following capabilities were already part of SentinelOps before the WebMCP Challenge work started:

- end-to-end incident lifecycle: Detect -> Investigate -> Decide -> Remediate -> Verify -> Report;
- FastAPI control plane and live dashboard;
- Google ADK + Gemini investigation and specialist agents;
- Cloud Logging / Log Router detection;
- Pub/Sub event delivery and workflow events;
- Firestore incident persistence;
- SentinelOps Node telemetry collection;
- human approval/rejection gate for high-impact remediation;
- allowlisted Cloud Run rollback with revision/service ownership checks;
- explicit execution confirmation;
- real post-remediation HTTP health verification;
- final incident reporting and resolved-state safeguards.

## WebMCP work added during the challenge

The WebMCP extension was added after the WebMCP Challenge submission period began. It makes the SentinelOps web application directly usable by compatible AI agents through browser-exposed structured tools while preserving the existing backend safety model.

The extension adds:

- a browser WebMCP bridge loaded by the SentinelOps dashboard;
- eight bounded incident-response tools registered through `document.modelContext.registerTool`;
- compatibility fallback for earlier `navigator.modelContext` implementations;
- a dashboard WebMCP availability/status indicator;
- an in-browser agent activity record for WebMCP tool calls;
- defensive client-side checks for controlled actions;
- runtime regression tests for registration, read operations, approval, execution, and verification gates.

## Exposed WebMCP tools

### Read-only

- `sentinelops_list_incidents`
- `sentinelops_get_incident`
- `sentinelops_list_events`
- `sentinelops_list_nodes`

### Controlled actions

- `sentinelops_approve_remediation`
- `sentinelops_reject_remediation`
- `sentinelops_execute_remediation`
- `sentinelops_verify_recovery`

## Safety architecture

WebMCP does not bypass or replace SentinelOps backend controls.

The bridge delegates controlled operations to the existing SentinelOps REST endpoints. The backend remains authoritative for:

- approval state;
- remediation policy;
- service allowlisting;
- target revision validation;
- service/revision ownership validation;
- explicit execution confirmation;
- post-remediation health verification.

The browser layer additionally refuses to execute a remediation unless the incident is already approved and the explicit WebMCP confirmation token is supplied. These browser checks are defense-in-depth only; the server-side checks are the security boundary.

SentinelOps still cannot report an incident as successfully resolved merely because an AI agent proposed or attempted an action. Recovery must be verified by the existing real health-check workflow.

## Human + agent demo flow

A representative WebMCP interaction is:

1. The user asks the agent to find the active production incident and inspect the evidence.
2. The agent calls `sentinelops_list_incidents` and `sentinelops_get_incident`.
3. The agent explains the evidence and proposed remediation.
4. If approval is pending, the agent stops for explicit human approval.
5. After the user approves, the agent calls `sentinelops_approve_remediation`.
6. After explicit instruction to execute, the agent calls `sentinelops_execute_remediation` with the approved target revision and confirmation token.
7. The agent calls `sentinelops_verify_recovery`.
8. SentinelOps performs the real HTTP health verification and only then allows the incident lifecycle to reach resolved/report state.

This demonstrates the intended collaboration model: the agent handles discovery, inspection, coordination, and bounded tool invocation, while SentinelOps retains deterministic policy controls and the human remains responsible for the high-impact approval decision.

## Browser testing

Open the SentinelOps dashboard in a WebMCP-capable browser environment. The dashboard registers the tool bridge automatically when `document.modelContext.registerTool` is available.

When WebMCP is unavailable, the normal SentinelOps dashboard continues to function; the WebMCP bridge fails closed and reports itself as unavailable rather than changing the core application behavior.

## Automated tests

Run:

```bash
python -m pytest -q
```

`tests/test_webmcp_bridge.py` verifies:

- the dashboard loads the WebMCP bridge;
- exactly the expected bounded tool set is registered;
- list operations execute against the existing REST API and bound their input limits;
- approval uses the existing backend approval endpoint;
- execution is refused without human approval;
- execution is refused without explicit WebMCP confirmation;
- approved execution delegates to the existing remediation endpoint;
- recovery verification is refused before remediation execution.

## Design principle

The WebMCP extension is intentionally an interface layer, not a second incident-response implementation.

`Human intent -> AI agent -> WebMCP -> SentinelOps control plane -> existing safety policy / remediation / verification workflow`

This keeps the project’s original safety guarantee intact while making the operational workflow directly usable by agents.
