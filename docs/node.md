# SentinelOps Node

The Node is a lightweight local process. It detects bounded signals locally and
sends normalized events to the Control Plane. It does not stream every log line
to Gemini.

## Local demo

Terminal 1 — Control Plane:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8080
```

Terminal 2 — SentinelOps Node:

```powershell
python -m src.node.agent --config node.yaml
```

Terminal 3 — demo service:

```powershell
python -m demo.broken_service
```

Terminal 4 — trigger the failure:

```powershell
python -m demo.generate_errors break
```

The Node observes the FATAL log rule and the three-failure health threshold,
then posts normalized events to `POST /events`. The Control Plane stores the
incident with bounded log/health evidence and sends it through the existing
approval workflow. Recover the demo service with:

```powershell
python -m demo.generate_errors recover
```

The next healthy healthcheck produces a recovery event. A remediation is not
considered resolved until a verification request passes.
