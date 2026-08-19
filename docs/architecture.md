# SentinelOps architecture

```mermaid
flowchart LR
    Event[Incident event] --> API[FastAPI on Cloud Run]
    API --> PubSub[Pub/Sub event bus]
    API --> Coordinator[Google ADK Incident Commander]
    Coordinator --> Logs[Log Analysis Agent]
    Coordinator --> Infra[Infrastructure Agent]
    Coordinator --> Code[Code Analysis Agent]
    Coordinator --> Remediate[Remediation Agent]
    Coordinator --> Verify[Verification Agent]
    Coordinator --> Gemini[Gemini 3.5 Flash]
    API --> Firestore[(Firestore incident state)]
    Remediate --> Gate{Human approval}
    Gate --> Action[Safe remediation executor]
    Action --> Verify
    Verify --> Report[Incident timeline and dashboard]
```

The local demo uses the same API and agent contract with deterministic evidence.
Its remediation executor mutates only the local incident state. A production
executor remains behind the approval boundary and must be explicitly configured.
