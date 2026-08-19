const state = { incident: null };
const $ = (id) => document.getElementById(id);
const workflowStages = ["detect", "investigate", "decide", "remediate", "verify", "report"];

function setSidebarCollapsed(collapsed) {
  const shell = document.querySelector(".shell");
  const toggle = $("sidebar-toggle");
  shell.classList.toggle("sidebar-collapsed", collapsed);
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
  toggle.querySelector("img").src = `/dashboard-assets/sheet/${collapsed ? "sidebar-expand" : "sidebar-collapse"}.png`;
  localStorage.setItem("sentinelops.sidebarCollapsed", String(collapsed));
}

const settings = {
  open: async () => {
    $("settings-backdrop").classList.remove("hidden");
    $("settings-backdrop").setAttribute("aria-hidden", "false");
    await settings.load();
    $("settings-close").focus();
  },
  close: () => {
    $("settings-backdrop").classList.add("hidden");
    $("settings-backdrop").setAttribute("aria-hidden", "true");
  },
  load: async () => {
    const response = await fetch("/settings");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Settings could not be loaded");
    $("settings-mode").value = payload.mode;
    $("settings-model").value = payload.model;
    $("settings-store").value = payload.store;
    $("settings-environment").value = payload.environment;
    $("settings-project").value = payload.project;
    $("settings-location").value = payload.location;
    $("settings-topic").value = payload.pubsub_topic;
    $("settings-subscription").value = payload.pubsub_subscription || "";
    $("settings-firestore-database").value = payload.firestore_database || "(default)";
    $("settings-pubsub").checked = payload.pubsub_enabled;
    $("settings-runtime").textContent = `${payload.mode.toUpperCase()} · ${payload.api_key_configured ? "API key configured" : "API key not configured"} · ${payload.save_target}`;
  },
  save: async (event) => {
    event.preventDefault();
    const status = $("settings-status");
    status.className = "settings-status";
    status.textContent = "Saving configuration…";
    status.classList.remove("hidden");
    try {
      const response = await fetch("/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        mode: $("settings-mode").value,
        model: $("settings-model").value,
        store: $("settings-store").value,
        environment: $("settings-environment").value,
        project: $("settings-project").value,
        location: $("settings-location").value,
        pubsub_topic: $("settings-topic").value,
        pubsub_subscription: $("settings-subscription").value,
        firestore_database: $("settings-firestore-database").value,
        pubsub_enabled: $("settings-pubsub").checked,
      }) });
      const payload = await response.json();
      if (!response.ok) { status.className = "settings-status error"; status.textContent = payload.detail || "Settings save failed"; return; }
      status.textContent = "Saved to .env. Restart the API to apply backend changes.";
      $("settings-runtime").textContent = `${payload.mode.toUpperCase()} · restart required · ${payload.save_target}`;
    } catch (error) {
      status.className = "settings-status error";
      status.textContent = error.message || "Settings save failed";
    }
  },
};

function setError(message) {
  const el = $("form-error");
  el.textContent = message || "";
  el.classList.toggle("hidden", !message);
}

function updateMetrics() {
  $("metric-active").textContent = state.incident ? "01" : "00";
}

function renderIncident(incident) {
  state.incident = incident;
  const analysis = incident.analysis || {};
  $("empty-state").classList.add("hidden");
  $("result-content").classList.remove("hidden");
  $("incident-title").textContent = `${incident.service} · ${incident.severity} severity`;
  $("incident-id").textContent = incident.incident_id;
  $("execution-mode").textContent = `${incident.execution_mode.toUpperCase()} EXECUTION`;
  $("root-cause").textContent = analysis.root_cause_hypothesis || "No hypothesis returned.";
  $("remediation").textContent = analysis.remediation_action || "No remediation plan returned.";
  const evidence = [...(incident.evidence || []), ...(analysis.evidence || [])];
  $("evidence-list").innerHTML = evidence.map((item) => {
    if (typeof item === "string") return `<li>${escapeHtml(item)}</li>`;
    const label = `${item.type || "evidence"} · ${item.source || "unknown source"}`;
    return `<li><strong>${escapeHtml(label)}</strong>${item.content ? ` — ${escapeHtml(item.content)}` : ""}</li>`;
  }).join("");
  const timeline = analysis.timeline || [];
  const workflowStages = new Set(["detect", "investigate", "decide", "remediate", "verify", "report"]);
  const stageTimeline = [...workflowStages].map((stage) => timeline.find((item) => item.stage === stage)).filter(Boolean);
  $("timeline-count").textContent = `${stageTimeline.length} / 6 stages`;
  $("timeline").innerHTML = stageTimeline.map((item) => `<div class="timeline-item ${item.status === "blocked" ? "blocked" : ""}"><span class="timeline-stage">${escapeHtml(item.stage)}</span><p>${escapeHtml(item.detail)}</p></div>`).join("");
  const badge = $("approval-badge");
  const remediationStatus = analysis.remediation_status || "planned";
  const verificationStatus = analysis.verification_status || "pending";
  badge.textContent = verificationStatus === "passed" ? "VERIFIED" : verificationStatus === "failed" ? "VERIFY FAILED" : remediationStatus === "executed" ? "EXECUTED" : (incident.approval_status || "not_required").replaceAll("_", " ").toUpperCase();
  badge.className = `status-badge ${verificationStatus === "passed" ? "executed" : verificationStatus === "failed" ? "rejected" : remediationStatus === "executed" ? "executed" : (incident.approval_status || "pending")}`;
  $("approval-note").textContent = analysis.execution_notes || "No approval is required.";
  const approvalNeeded = incident.approval_status === "pending";
  $("approve-button").disabled = !approvalNeeded;
  $("reject-button").disabled = !approvalNeeded;
  $("execute-button").disabled = incident.approval_status !== "approved" || remediationStatus === "executed";
  $("verify-button").disabled = remediationStatus !== "executed" || verificationStatus !== "pending";
  updateMetrics();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char]));
}

const controlPanel = {
  close: () => {
    $("control-backdrop").classList.add("hidden");
    $("control-backdrop").setAttribute("aria-hidden", "true");
  },
  open: async (kind) => {
    $("control-backdrop").classList.remove("hidden");
    $("control-backdrop").setAttribute("aria-hidden", "false");
    if (kind === "safety") {
      $("control-eyebrow").textContent = "SAFETY POLICY";
      $("control-title").textContent = "Permission boundaries";
      $("control-intro").textContent = "SentinelOps keeps high-impact remediation behind an explicit human decision.";
      $("control-body").innerHTML = `<div class="policy-list"><div class="policy-row"><img src="/dashboard-assets/sheet/shield-check.png" alt="" /><div><strong>Human approval required</strong><p>High-risk actions remain blocked until an operator approves the proposed remediation.</p></div><span class="locked-pill">LOCKED</span></div><div class="policy-row"><img src="/dashboard-assets/sheet/stop.png" alt="" /><div><strong>Production mutation disabled</strong><p>Demo execution changes only the stored incident state. No production system is connected.</p></div><span class="locked-pill">SAFE</span></div><div class="policy-row"><img src="/dashboard-assets/sheet/refresh.png" alt="" /><div><strong>Verification required</strong><p>Every simulated action must pass an explicit verification step before the workflow is complete.</p></div><span class="locked-pill">ON</span></div></div>`;
    } else if (kind === "nodes") {
      $("control-eyebrow").textContent = "NODE OPERATIONS";
      $("control-title").textContent = "SentinelOps Nodes";
      $("control-intro").textContent = "Live heartbeat state, monitored services, and incidents currently assigned to each Node.";
      const response = await fetch("/nodes");
      const nodes = response.ok ? await response.json() : [];
      const formatSeen = (value) => value ? new Date(value).toLocaleString() : "No heartbeat";
      $("control-body").innerHTML = nodes.length ? `<div class="node-grid">${nodes.map((node) => `<article class="node-card"><div class="node-card-header"><div><strong>${escapeHtml(node.node_id)}</strong><p class="muted">${escapeHtml(node.hostname || "Unknown host")} · ${escapeHtml(node.platform)}</p></div><span class="node-status ${node.status === "offline" ? "offline" : ""}">${escapeHtml(node.status)}</span></div><div class="node-card-meta"><span>Last heartbeat<strong>${escapeHtml(formatSeen(node.last_seen))}</strong></span><span>Active incidents<strong>${node.active_incidents}</strong></span><span>Node version<strong>${escapeHtml(node.version)}</strong></span><span>Services<strong>${node.services.length}</strong></span></div><p class="node-services">${node.services.length ? `Monitored: ${escapeHtml(node.services.join(", "))}` : "No monitored services reported."}</p></article>`).join("")}</div>` : `<div class="control-card"><strong>No Nodes registered</strong><p>Start a SentinelOps Node and its heartbeat will appear here automatically.</p></div>`;
    } else {
      $("control-eyebrow").textContent = "WORKFLOW OBSERVABILITY";
      $("control-title").textContent = "Workflow control plane";
      $("control-intro").textContent = "Six stages from detection to a verified incident report, plus the latest local history.";
      const [incidentResponse, eventResponse] = await Promise.all([fetch("/incidents?limit=8"), fetch("/events?limit=8")]);
      const incidents = incidentResponse.ok ? await incidentResponse.json() : [];
      const events = eventResponse.ok ? await eventResponse.json() : [];
      const timeline = state.incident?.analysis?.timeline || [];
      const stageCards = workflowStages.map((stage) => {
        const event = timeline.find((item) => item.stage === stage);
        const status = event?.status || "pending";
        return `<div class="control-card"><span class="stage-status ${status}">${status}</span><strong>${stage}</strong><p>${escapeHtml(event?.detail || "Waiting for the next incident run.")}</p></div>`;
      }).join("");
      $("control-body").innerHTML = `<div class="control-grid">${stageCards}</div><div class="section-row" style="margin-top:18px"><span class="block-label">RECENT INCIDENTS</span><span class="muted" id="history-count">${incidents.length} loaded</span></div><div class="history-tools"><input id="history-search" placeholder="Search service or incident ID" aria-label="Search incident history" /><select id="history-status" aria-label="Filter incident status"><option value="all">All statuses</option><option value="pending">Pending approval</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="not_required">Not required</option></select></div><div class="history-list" id="history-list"></div><div class="section-row" style="margin-top:18px"><span class="block-label">EVENT STREAM</span><span class="muted">${events.length} events</span></div><div class="event-list" id="event-list"></div><div class="event-detail hidden" id="event-detail" aria-live="polite"></div>`;
      const renderHistory = () => {
        const query = $("history-search").value.trim().toLowerCase();
        const status = $("history-status").value;
        const filtered = incidents.filter((incident) => {
          const searchable = `${incident.service} ${incident.incident_id} ${incident.severity}`.toLowerCase();
          return (!query || searchable.includes(query)) && (status === "all" || incident.approval_status === status);
        });
        $("history-count").textContent = `${filtered.length} of ${incidents.length} loaded`;
        $("history-list").innerHTML = filtered.length ? filtered.map((incident) => `<button class="history-item" type="button" data-incident-id="${escapeHtml(incident.incident_id)}"><div><strong>${escapeHtml(incident.service)} · ${escapeHtml(incident.severity)}</strong><small>${escapeHtml(incident.incident_id)} · ${escapeHtml(incident.status)}</small></div><span class="status-badge ${incident.approval_status}">${escapeHtml(incident.approval_status.replaceAll("_", " "))}</span></button>`).join("") : `<p class="muted">No matching incidents.</p>`;
      };
      const renderEvents = () => {
        $("event-list").innerHTML = events.length ? events.map((event) => `<button class="event-item" type="button" data-event-id="${escapeHtml(event.event_id)}"><strong>${escapeHtml(event.event_type)}</strong><small>${escapeHtml(new Date(event.occurred_at).toLocaleTimeString())}</small></button>`).join("") : `<p class="muted">No workflow events have been recorded yet.</p>`;
      };
      renderHistory();
      renderEvents();
      $("history-search").addEventListener("input", renderHistory);
      $("history-status").addEventListener("change", renderHistory);
      $("event-list").addEventListener("click", (event) => {
        const target = event.target.closest("[data-event-id]");
        if (!target) return;
        const record = events.find((item) => item.event_id === target.dataset.eventId);
        if (!record) return;
        $("event-detail").classList.remove("hidden");
        $("event-detail").innerHTML = `<strong>${escapeHtml(record.event_type)} · ${escapeHtml(record.event_id)}</strong><pre>${escapeHtml(JSON.stringify(record.payload, null, 2))}</pre>`;
      });
    }
    $("control-close").focus();
  },
};

async function createIncident(service, severity, summary) {
  setError("");
  const response = await fetch("/incidents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ service, severity, summary }) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Incident analysis failed");
  renderIncident(payload);
}

async function decide(decision) {
  if (!state.incident) return;
  const response = await fetch(`/incidents/${state.incident.incident_id}/approval`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, comment: $("approval-comment").value }) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Approval update failed");
  $("approval-comment").value = "";
  renderIncident(payload);
}

async function executeRemediation() {
  if (!state.incident) return;
  const response = await fetch(`/incidents/${state.incident.incident_id}/execute`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Safe action failed");
  renderIncident(payload);
}

async function verifyRemediation() {
  if (!state.incident) return;
  const evidence = [...(state.incident.evidence || []), ...(state.incident.analysis?.evidence || [])];
  const healthEvidence = evidence.find((item) => typeof item === "object" && item.type === "healthcheck" && item.source);
  const endpoint = healthEvidence ? `/incidents/${state.incident.incident_id}/verify/health` : `/incidents/${state.incident.incident_id}/verify`;
  const body = healthEvidence ? { url: healthEvidence.source, expected_status: healthEvidence.status_code || 200 } : { passed: true, notes: "Local demo health checks passed." };
  const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Verification failed");
  renderIncident(payload);
}

async function refreshNodeStatus() {
  try {
    const response = await fetch("/nodes");
    if (!response.ok) return;
    const nodes = await response.json();
    const online = nodes.filter((node) => node.status === "online");
    $("node-card-title").textContent = online.length ? `${online.length} Node${online.length === 1 ? "" : "s"} online` : "Demo environment";
    $("node-card-status").textContent = online.length ? online.map((node) => `${node.node_id} · ${node.platform}`).join(" · ") : "Waiting for Node heartbeat";
  } catch (_) {
    // The dashboard remains usable when the optional Node registry is offline.
  }
}

$("incident-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await createIncident($("service").value, $("severity").value, $("summary").value); } catch (error) { setError(error.message); }
});
$("demo-button").addEventListener("click", async () => {
  $("service").value = "payments-api";
  $("severity").value = "high";
  $("summary").value = "HTTP 500 rate increased after revision payments-api-v2 deployed 6 minutes ago";
  try { await createIncident($("service").value, $("severity").value, $("summary").value); } catch (error) { setError(error.message); }
});
$("approve-button").addEventListener("click", async () => { try { await decide("approve"); } catch (error) { setError(error.message); } });
$("reject-button").addEventListener("click", async () => { try { await decide("reject"); } catch (error) { setError(error.message); } });
$("execute-button").addEventListener("click", async () => { try { await executeRemediation(); } catch (error) { setError(error.message); } });
$("verify-button").addEventListener("click", async () => { try { await verifyRemediation(); } catch (error) { setError(error.message); } });
$("settings-button").addEventListener("click", () => { settings.open().catch((error) => { const status = $("settings-status"); status.className = "settings-status error"; status.textContent = error.message; status.classList.remove("hidden"); }); });
$("settings-close").addEventListener("click", settings.close);
$("settings-cancel").addEventListener("click", settings.close);
$("settings-form").addEventListener("submit", settings.save);
$("settings-backdrop").addEventListener("click", (event) => { if (event.target === $("settings-backdrop")) settings.close(); });
$("workflow-nav").addEventListener("click", async (event) => { event.preventDefault(); try { await controlPanel.open("workflow"); } catch (error) { setError(error.message); } });
$("safety-nav").addEventListener("click", async (event) => { event.preventDefault(); try { await controlPanel.open("safety"); } catch (error) { setError(error.message); } });
$("node-card").addEventListener("click", async () => { try { await controlPanel.open("nodes"); } catch (error) { setError(error.message); } });
$("node-card").addEventListener("keydown", async (event) => { if (event.key !== "Enter" && event.key !== " ") return; event.preventDefault(); try { await controlPanel.open("nodes"); } catch (error) { setError(error.message); } });
$("incidents-nav").addEventListener("click", (event) => { event.preventDefault(); controlPanel.close(); $("service").focus(); });
$("control-close").addEventListener("click", controlPanel.close);
$("control-backdrop").addEventListener("click", (event) => { if (event.target === $("control-backdrop")) controlPanel.close(); });
$("control-body").addEventListener("click", async (event) => {
  const target = event.target.closest("[data-incident-id]");
  if (!target) return;
  try {
    const response = await fetch(`/incidents/${encodeURIComponent(target.dataset.incidentId)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Incident could not be loaded");
    renderIncident(payload);
    controlPanel.close();
  } catch (error) {
    setError(error.message);
    controlPanel.close();
  }
});
$("sidebar-toggle").addEventListener("click", () => {
  setSidebarCollapsed(!document.querySelector(".shell").classList.contains("sidebar-collapsed"));
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!$ ("settings-backdrop").classList.contains("hidden")) settings.close();
  if (!$ ("control-backdrop").classList.contains("hidden")) controlPanel.close();
});
setSidebarCollapsed(localStorage.getItem("sentinelops.sidebarCollapsed") === "true");
updateMetrics();
refreshNodeStatus();
window.setInterval(refreshNodeStatus, 15000);
