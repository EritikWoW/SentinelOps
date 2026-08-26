(() => {
  "use strict";

  const TOOL_VERSION = "2026-08-26";
  const activity = [];

  function modelContext() {
    return document.modelContext || navigator.modelContext || null;
  }

  function setStatus(label, state = "ready") {
    let badge = document.getElementById("webmcp-status");
    if (!badge) {
      const host = document.querySelector(".monitoring-badges");
      if (!host) return;
      badge = document.createElement("span");
      badge.id = "webmcp-status";
      badge.className = "locked-pill";
      host.appendChild(badge);
    }
    badge.textContent = `WEBMCP ${label}`;
    badge.dataset.state = state;
    badge.title = "SentinelOps WebMCP tool bridge";
  }

  function recordActivity(tool, status, detail = "") {
    const entry = {
      timestamp: new Date().toISOString(),
      tool,
      status,
      detail: String(detail || "").slice(0, 500),
    };
    activity.unshift(entry);
    if (activity.length > 50) activity.length = 50;
    const previous = window.SentinelOpsWebMCP || {};
    window.SentinelOpsWebMCP = {
      ...previous,
      version: TOOL_VERSION,
      tools: Array.isArray(previous.tools) ? previous.tools.slice() : REGISTERED_TOOL_NAMES.slice(),
      activity: activity.slice(),
    };
    window.dispatchEvent(new CustomEvent("sentinelops:webmcp-activity", { detail: entry }));
  }

  async function requestJson(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

    const response = await fetch(url, {
      cache: "no-store",
      ...options,
      headers,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = payload.detail || `${response.status} ${response.statusText}`;
      throw new Error(message);
    }
    return payload;
  }

  function asToolResult(value) {
    return JSON.stringify(value, null, 2);
  }

  function boundedLimit(value, fallback, max) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(1, Math.min(parsed, max));
  }

  function deriveHealthUrl(incident) {
    const evidence = [...(incident?.evidence || []), ...(incident?.analysis?.evidence || [])];
    for (const item of evidence) {
      if (item && typeof item === "object" && item.type === "healthcheck" && /^https?:\/\//.test(item.source || "")) {
        return item.source;
      }
      const text = typeof item === "string" ? item : item?.content || "";
      const match = String(text).match(/https?:\/\/[^\s"']+\/health\b/i);
      if (match) return match[0];
    }
    return String(incident?.summary || "").match(/https?:\/\/[^\s"']+\/health\b/i)?.[0] || "";
  }

  async function runTool(name, fn) {
    recordActivity(name, "started");
    try {
      const result = await fn();
      recordActivity(name, "succeeded");
      return asToolResult(result);
    } catch (error) {
      recordActivity(name, "failed", error?.message || error);
      throw error;
    }
  }

  const tools = [
    {
      name: "sentinelops_list_incidents",
      description: "List recent SentinelOps incidents. Use this first to discover active or recently resolved incidents before inspecting or acting on one.",
      inputSchema: {
        type: "object",
        properties: {
          limit: {
            type: "integer",
            minimum: 1,
            maximum: 100,
            description: "Maximum number of recent incidents to return. Defaults to 25.",
          },
        },
      },
      annotations: { readOnlyHint: true },
      execute: ({ limit = 25 } = {}) => runTool("sentinelops_list_incidents", async () => {
        const incidents = await requestJson(`/incidents?limit=${boundedLimit(limit, 25, 100)}`);
        return {
          count: incidents.length,
          incidents,
        };
      }),
    },
    {
      name: "sentinelops_get_incident",
      description: "Inspect one SentinelOps incident in detail, including evidence, root-cause hypothesis, remediation plan, approval state, workflow timeline, and verification state.",
      inputSchema: {
        type: "object",
        properties: {
          incident_id: { type: "string", description: "SentinelOps incident identifier." },
        },
        required: ["incident_id"],
      },
      annotations: { readOnlyHint: true },
      execute: ({ incident_id }) => runTool("sentinelops_get_incident", () =>
        requestJson(`/incidents/${encodeURIComponent(incident_id)}`)
      ),
    },
    {
      name: "sentinelops_list_events",
      description: "List recent SentinelOps workflow and detector events for operational context and auditability.",
      inputSchema: {
        type: "object",
        properties: {
          limit: {
            type: "integer",
            minimum: 1,
            maximum: 100,
            description: "Maximum number of recent events to return. Defaults to 25.",
          },
        },
      },
      annotations: { readOnlyHint: true },
      execute: ({ limit = 25 } = {}) => runTool("sentinelops_list_events", async () => {
        const events = await requestJson(`/events?limit=${boundedLimit(limit, 25, 100)}`);
        return { count: events.length, events };
      }),
    },
    {
      name: "sentinelops_list_nodes",
      description: "List registered SentinelOps Nodes and their current liveness, monitored services, and active incident counts.",
      inputSchema: { type: "object", properties: {} },
      annotations: { readOnlyHint: true },
      execute: () => runTool("sentinelops_list_nodes", async () => {
        const nodes = await requestJson("/nodes");
        return { count: nodes.length, nodes };
      }),
    },
    {
      name: "sentinelops_approve_remediation",
      description: "Record explicit human approval for a pending SentinelOps remediation. Call only after the user has clearly approved the proposed high-impact action. This does not execute the remediation.",
      inputSchema: {
        type: "object",
        properties: {
          incident_id: { type: "string", description: "Incident awaiting approval." },
          comment: { type: "string", description: "Optional human approval note." },
        },
        required: ["incident_id"],
      },
      annotations: { readOnlyHint: false },
      execute: ({ incident_id, comment = "Approved through WebMCP after explicit human instruction." }) =>
        runTool("sentinelops_approve_remediation", async () => {
          const incident = await requestJson(`/incidents/${encodeURIComponent(incident_id)}`);
          if (incident.approval_status !== "pending") {
            throw new Error(`Incident approval state is '${incident.approval_status}', not 'pending'.`);
          }
          return requestJson(`/incidents/${encodeURIComponent(incident_id)}/approval`, {
            method: "POST",
            body: JSON.stringify({ decision: "approve", comment }),
          });
        }),
    },
    {
      name: "sentinelops_reject_remediation",
      description: "Reject a pending SentinelOps remediation after explicit human instruction. Rejection prevents the proposed high-impact action from being executed.",
      inputSchema: {
        type: "object",
        properties: {
          incident_id: { type: "string", description: "Incident awaiting approval." },
          comment: { type: "string", description: "Optional human rejection note." },
        },
        required: ["incident_id"],
      },
      annotations: { readOnlyHint: false },
      execute: ({ incident_id, comment = "Rejected through WebMCP after explicit human instruction." }) =>
        runTool("sentinelops_reject_remediation", async () => {
          const incident = await requestJson(`/incidents/${encodeURIComponent(incident_id)}`);
          if (incident.approval_status !== "pending") {
            throw new Error(`Incident approval state is '${incident.approval_status}', not 'pending'.`);
          }
          return requestJson(`/incidents/${encodeURIComponent(incident_id)}/approval`, {
            method: "POST",
            body: JSON.stringify({ decision: "reject", comment }),
          });
        }),
    },
    {
      name: "sentinelops_execute_remediation",
      description: "Execute an already approved, allowlisted Cloud Run rollback. The incident must already have human approval. The backend independently enforces approval, policy, service allowlisting, revision ownership, and explicit execution confirmation.",
      inputSchema: {
        type: "object",
        properties: {
          incident_id: { type: "string", description: "Approved incident to remediate." },
          target_revision: { type: "string", description: "Explicit known-healthy Cloud Run revision that belongs to the incident service." },
          region: { type: "string", description: "Cloud Run region. Defaults to europe-west1." },
          confirmation: {
            type: "string",
            enum: ["EXECUTE_APPROVED_REMEDIATION"],
            description: "Explicit execution confirmation token. Use only after the user has asked to execute the approved remediation.",
          },
        },
        required: ["incident_id", "target_revision", "confirmation"],
      },
      annotations: { readOnlyHint: false },
      execute: ({ incident_id, target_revision, region = "europe-west1", confirmation }) =>
        runTool("sentinelops_execute_remediation", async () => {
          if (confirmation !== "EXECUTE_APPROVED_REMEDIATION") {
            throw new Error("Explicit WebMCP execution confirmation is required.");
          }
          const incident = await requestJson(`/incidents/${encodeURIComponent(incident_id)}`);
          if (incident.approval_status !== "approved") {
            throw new Error("Human approval is required before remediation execution.");
          }
          if (incident?.analysis?.remediation_status === "blocked") {
            throw new Error("SentinelOps safety policy has blocked this remediation.");
          }
          return requestJson(`/incidents/${encodeURIComponent(incident_id)}/execute`, {
            method: "POST",
            body: JSON.stringify({
              confirm: true,
              action: "cloud_run_rollback",
              target_revision,
              region,
            }),
          });
        }),
    },
    {
      name: "sentinelops_verify_recovery",
      description: "Run SentinelOps real HTTP health verification after remediation. A successful remediation is not considered resolved until this verification passes.",
      inputSchema: {
        type: "object",
        properties: {
          incident_id: { type: "string", description: "Remediated incident to verify." },
          health_url: { type: "string", description: "Optional explicit health URL. If omitted, SentinelOps derives it from incident evidence." },
          expected_status: { type: "integer", minimum: 100, maximum: 599, description: "Expected HTTP status. Defaults to 200." },
          timeout_seconds: { type: "integer", minimum: 1, maximum: 30, description: "Health request timeout. Defaults to 5 seconds." },
        },
        required: ["incident_id"],
      },
      annotations: { readOnlyHint: false },
      execute: ({ incident_id, health_url, expected_status = 200, timeout_seconds = 5 }) =>
        runTool("sentinelops_verify_recovery", async () => {
          const incident = await requestJson(`/incidents/${encodeURIComponent(incident_id)}`);
          if (incident?.analysis?.remediation_status !== "executed") {
            throw new Error("Remediation must be executed before recovery verification.");
          }
          const url = health_url || deriveHealthUrl(incident);
          if (!url) throw new Error("No health endpoint was found in incident evidence; provide health_url explicitly.");
          return requestJson(`/incidents/${encodeURIComponent(incident_id)}/verify/health`, {
            method: "POST",
            body: JSON.stringify({
              url,
              expected_status: Number(expected_status) || 200,
              timeout_seconds: Math.max(1, Math.min(Number(timeout_seconds) || 5, 30)),
            }),
          });
        }),
    },
  ];

  const REGISTERED_TOOL_NAMES = tools.map((tool) => tool.name);

  async function registerWebMCP() {
    const context = modelContext();
    if (!context || typeof context.registerTool !== "function") {
      setStatus("UNAVAILABLE", "unavailable");
      window.SentinelOpsWebMCP = {
        version: TOOL_VERSION,
        tools: [],
        activity: [],
        available: false,
      };
      return;
    }

    try {
      for (const tool of tools) {
        await context.registerTool(tool);
      }
      setStatus(`${tools.length} TOOLS`, "ready");
      window.SentinelOpsWebMCP = {
        version: TOOL_VERSION,
        tools: REGISTERED_TOOL_NAMES.slice(),
        activity: activity.slice(),
        available: true,
      };
      recordActivity("webmcp", "registered", `${tools.length} tools registered`);
      console.info(`[SentinelOps] WebMCP ready: ${tools.length} tools registered.`);
    } catch (error) {
      setStatus("ERROR", "error");
      window.SentinelOpsWebMCP = {
        version: TOOL_VERSION,
        tools: [],
        activity: activity.slice(),
        available: false,
      };
      recordActivity("webmcp", "failed", error?.message || error);
      console.error("[SentinelOps] WebMCP registration failed", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", registerWebMCP, { once: true });
  } else {
    registerWebMCP();
  }
})();
