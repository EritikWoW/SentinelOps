/* Live system-summary semantics for the top metric cards. */

function metricLabel(metricId, value) {
  const label = $(metricId)?.closest(".metric-card")?.querySelector(".metric-label");
  if (label) label.textContent = value;
}

function activeIncidentSummary(active, pending) {
  if (!active.length) return "● No unresolved incidents";
  if (active.length === 1 && pending === 1) return "● 1 awaiting approval";
  if (active.length === 1) return "● 1 active incident";
  if (pending > 0) return `● ${active.length} active · ${pending} awaiting approval`;
  return `● ${active.length} active incidents`;
}

function automationMetric(active, latest) {
  const runtime = state.runtime;
  if (!runtime) return { value: "STARTING", foot: "● Loading runtime state", state: "attention" };
  if (runtime.mode !== "gemini") return { value: "SIMULATION", foot: "● Demo execution mode active", state: "attention" };
  if (!runtime.pubsub_enabled) return { value: "DEGRADED", foot: "● Detector event publishing is disabled", state: "danger" };

  const safety = `SAFE · approval + ${runtime.live_remediation_enabled ? "live allowlist" : "bounded actions"} + verification`;
  if (!latest || !active.length) return { value: "MONITORING", foot: `● ${safety}`, state: "ok" };

  const analysis = latest.analysis || {};
  const workflow = deriveWorkflowState(latest);
  if (latest.status === "remediation_failed" || analysis.verification_status === "failed") {
    return { value: "DEGRADED", foot: `● ${latest.incident_id} · remediation or verification failed`, state: "danger" };
  }
  if (analysis.remediation_status === "executed" && analysis.verification_status === "pending") {
    return { value: "VERIFYING", foot: `● ${latest.incident_id} · recovery check in progress`, state: "attention" };
  }
  if (latest.approval_status === "approved" && analysis.remediation_status !== "executed") {
    return { value: "AUTHORIZED", foot: `● ${latest.incident_id} · approved remediation ready`, state: "attention" };
  }
  if (latest.approval_status === "pending") {
    return { value: "APPROVAL", foot: `● ${latest.incident_id} · human decision required`, state: "attention" };
  }
  if (latest.approval_status === "rejected") {
    return { value: "BLOCKED", foot: `● ${latest.incident_id} · remediation rejected`, state: "danger" };
  }

  const labels = {
    DETECTING: "DETECTING",
    INVESTIGATING: "INVESTIGATING",
    DECIDING: "DECIDING",
    DECIDED: "DECIDED",
    VERIFYING: "VERIFYING",
  };
  return {
    value: labels[workflow.label] || workflow.label || "ACTIVE",
    foot: `● ${latest.incident_id} · ${safety}`,
    state: "attention",
  };
}

function updateMetrics() {
  const active = state.incidents.filter(isActiveIncident);
  const latest = active[0] || null;
  const pending = active.filter((incident) => incident.approval_status === "pending").length;

  metricLabel("metric-active", "ACTIVE INCIDENTS");
  $("metric-active").textContent = String(active.length).padStart(2, "0");
  $("metric-active-foot").textContent = activeIncidentSummary(active, pending);
  setMetricState("metric-active", active.length ? "attention" : "ok");

  metricLabel("metric-workflow", "WORKFLOW");
  if (!latest) {
    $("metric-workflow").textContent = "IDLE";
    $("metric-workflow-foot").textContent = "Waiting for detector event";
    setMetricState("metric-workflow", "ok");
  } else {
    const workflow = deriveWorkflowState(latest);
    $("metric-workflow").textContent = `${completedStages(latest)}/6`;
    $("metric-workflow-foot").textContent = `${workflow.label} · ${latest.incident_id}`;
    setMetricState("metric-workflow", workflow.state === "failed" || workflow.state === "rejected" ? "danger" : "attention");
  }

  metricLabel("metric-policy", "AUTOMATION");
  const automation = automationMetric(active, latest);
  $("metric-policy").textContent = automation.value;
  $("metric-policy-foot").textContent = automation.foot;
  setMetricState("metric-policy", automation.state);
}

// dashboard.js starts the refresh loop before this file loads. Re-render once so
// the new semantics are visible immediately; later refreshes call this override.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => updateMetrics(), { once: true });
} else {
  updateMetrics();
}
