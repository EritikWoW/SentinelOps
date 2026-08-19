# Tools and safety

SentinelOps tools are typed and permission-scoped:

| Action | Policy |
| --- | --- |
| `read_logs` | automatic, read-only |
| `health_check` | automatic, read-only |
| `read_process_state` | automatic, read-only |
| `restart_process` | explicit approval; unsupported without adapter |
| `restart_service` | explicit approval; unsupported without adapter |
| `rollback` | explicit approval |
| `delete_resource` | blocked |

Gemini receives bounded evidence and may call only the read-only ADK tools. It
cannot execute arbitrary shell commands. Remediation adapters return
`supported: false` and `executed: false` until a host-specific adapter is
explicitly configured.
