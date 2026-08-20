const $ = (id) => document.getElementById(id);
const workflowStages = ["detect", "investigate", "decide", "remediate", "verify", "report"];
const state = { incident: null, incidents: [], events: [], runtime: null, nodes: [], view: "incidents", autoSelected: true };

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char]));
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  return payload;
}

function setError(message) {
  const element = $("form-error");
  if (!element) return;
  element.textContent = message || "";
  element.classList.toggle("hidden", !message);
}

function isActiveIncident(incident) {
  return !["resolved", "remediation_failed", "archived"].includes(incident.status);
}

function completedStages(incident) {
  const timeline = incident?.analysis?.timeline || [];
  return new Set(timeline.filter((item) => item.status === "completed").map((item) => item.stage)).size;
}

function deriveWorkflowState(incident) {
  if (!incident) return { label: "WAITING", state: "waiting" };
  const analysis = incident.analysis || {};
  const completed = new Set((analysis.timeline || []).filter((item) => item.status === "completed").map((item) => item.stage));
  if (incident.status === "archived") return { label: "ARCHIVED", state: "waiting" };
  if (incident.status === "resolved" || analysis.verification_status === "passed") return { label: "RESOLVED", state: "resolved" };
  if (incident.status === "remediation_failed" || analysis.verification_status === "failed") return { label: "FAILED", state: "failed" };
  if (analysis.remediation_status === "executed") return { label: "VERIFYING", state: "verifying" };
  if (incident.approval_status === "approved") return { label: "AUTHORIZED", state: "authorized" };
  if (incident.approval_status === "rejected") return { label: "REJECTED", state: "rejected" };
  if (incident.approval_status === "pending") return { label: "AWAITING APPROVAL", state: "approval" };
  if (completed.has("decide")) return { label: "DECIDED", state: "deciding" };
  if (completed.has("investigate")) return { label: "DECIDING", state: "deciding" };
  if (completed.has("detect")) return { label: "INVESTIGATING", state: "investigating" };
  return { label: "DETECTING", state: "detecting" };
}

function setMetricState(elementId, metricState) {
  const card = $(elementId)?.closest(".metric-card");
  if (card) card.dataset.state = metricState;
}

function updateMetrics() {
  const active = state.incidents.filter(isActiveIncident);
  const latest = active[0] || null;
  const pending = active.filter((incident) => incident.approval_status === "pending").length;
  $("metric-active").textContent = String(active.length).padStart(2, "0");
  $("metric-active-foot").textContent = active.length ? `● ${pending} awaiting approval` : "● No unresolved incidents";
  setMetricState("metric-active", active.length ? "attention" : "ok");

  $("metric-workflow").textContent = latest ? `${completedStages(latest)}/6` : "0/6";
  $("metric-workflow-foot").textContent = latest ? `${latest.incident_id} · ${deriveWorkflowState(latest).label.toLowerCase()}` : "No active workflow";
  setMetricState("metric-workflow", latest?.status === "remediation_failed" ? "danger" : "ok");

  const live = state.runtime?.mode === "gemini";
  const remediation = Boolean(state.runtime?.live_remediation_enabled);
  $("metric-policy").textContent = live ? "SAFE" : "SIM";
  $("metric-policy-foot").textContent = live
    ? `● Approval + ${remediation ? "live allowlist" : "bounded actions"} + verification`
    : "● Simulation mode active";
  setMetricState("metric-policy", "ok");
}

function evidenceText(item) {
  if (typeof item === "string") return escapeHtml(item);
  const label = `${item?.type || "evidence"} · ${item?.source || "unknown source"}`;
  return `<strong>${escapeHtml(label)}</strong>${item?.content ? ` — ${escapeHtml(item.content)}` : ""}`;
}

function renderIncident(incident) {
  state.incident = incident;
  const analysis = incident.analysis || {};
  $("empty-state").classList.add("hidden");
  $("result-content").classList.remove("hidden");
  $("incident-title").textContent = `${incident.service} · ${incident.severity} severity`;
  $("incident-id").textContent = incident.incident_id;
  $("execution-mode").textContent = `${String(incident.execution_mode || "unknown").toUpperCase()} EXECUTION`;
  $("root-cause").textContent = analysis.root_cause_hypothesis || "No hypothesis returned.";
  $("remediation").textContent = analysis.remediation_action || "No remediation plan returned.";
  const evidence = [...(incident.evidence || []), ...(analysis.evidence || [])];
  $("evidence-list").innerHTML = evidence.length ? evidence.map((item) => `<li>${evidenceText(item)}</li>`).join("") : "<li>No evidence recorded.</li>";

  const timeline = analysis.timeline || [];
  const stageTimeline = workflowStages.map((stage) => timeline.find((item) => item.stage === stage)).filter(Boolean);
  $("timeline-count").textContent = `${completedStages(incident)} / 6 completed`;
  $("timeline").innerHTML = stageTimeline.length
    ? stageTimeline.map((item) => `<div class="timeline-item ${item.status === "blocked" ? "blocked" : ""}"><span class="timeline-stage">${escapeHtml(item.stage)}</span><p>${escapeHtml(item.detail)}</p></div>`).join("")
    : `<p class="muted">Workflow timeline has not been recorded yet.</p>`;

  const workflow = deriveWorkflowState(incident);
  $("workflow-state").textContent = workflow.label;
  $("workflow-state").className = `workflow-state ${workflow.state}`;

  const remediationStatus = analysis.remediation_status || "planned";
  const verificationStatus = analysis.verification_status || "pending";
  const badge = $("approval-badge");
  badge.textContent = incident.status === "archived" ? "ARCHIVED" : verificationStatus === "passed" ? "VERIFIED" : verificationStatus === "failed" ? "VERIFY FAILED" : remediationStatus === "executed" ? "EXECUTED" : String(incident.approval_status || "not_required").replaceAll("_", " ").toUpperCase();
  badge.className = `status-badge ${incident.status === "archived" ? "rejected" : verificationStatus === "passed" ? "executed" : verificationStatus === "failed" ? "rejected" : remediationStatus === "executed" ? "executed" : (incident.approval_status || "pending")}`;

  const reportEvent = timeline.find((item) => item.stage === "report" && item.status === "completed");
  $("report-section").classList.toggle("hidden", !reportEvent);
  $("report-detail").textContent = reportEvent?.detail || "";
  $("report-status").textContent = incident.status === "resolved" ? "RESOLVED" : "FINAL";
  $("report-status").className = `report-status ${incident.status === "resolved" ? "resolved" : ""}`;

  $("approval-note").textContent = analysis.execution_notes || (incident.approval_status === "pending" ? "High-impact remediation requires explicit human approval." : "No pending approval action.");
  const approvalNeeded = incident.approval_status === "pending" && incident.status !== "archived";
  $("approve-button").disabled = !approvalNeeded;
  $("reject-button").disabled = !approvalNeeded;
  $("execute-button").disabled = incident.approval_status !== "approved" || remediationStatus === "executed" || incident.status === "archived";
  $("verify-button").disabled = remediationStatus !== "executed" || verificationStatus !== "pending";
  $("execution-targets").classList.toggle("hidden", incident.approval_status !== "approved" || remediationStatus === "executed");
  if (incident.approval_status === "approved" && !$("target-revision").value) $("target-revision").value = inferTargetRevision(incident);
  renderWorkflow();
}

function clearIncident() {
  state.incident = null;
  $("result-content").classList.add("hidden");
  $("empty-state").classList.remove("hidden");
  $("target-revision").value = "";
  renderWorkflow();
}

function inferTargetRevision(incident) {
  const service = String(incident?.service || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (!service) return "";
  const pattern = new RegExp(`${service}-\\d{5}-[a-z0-9]+`, "gi");
  const text = [incident?.analysis?.execution_notes || "", incident?.analysis?.remediation_action || ""].join(" ");
  const candidates = text.match(pattern) || [];
  const failing = new Set((incident?.evidence || []).flatMap((item) => String(typeof item === "string" ? item : item?.content || "").match(pattern) || []));
  return candidates.find((revision) => !failing.has(revision)) || candidates[0] || "";
}

function deriveHealthUrl(incident) {
  const evidence = [...(incident?.evidence || []), ...(incident?.analysis?.evidence || [])];
  for (const item of evidence) {
    if (item && typeof item === "object" && item.type === "healthcheck" && /^https?:\/\//.test(item.source || "")) return item.source;
    const text = typeof item === "string" ? item : item?.content || "";
    const match = String(text).match(/https?:\/\/[^\s"']+\/health\b/i);
    if (match) return match[0];
  }
  return String(incident?.summary || "").match(/https?:\/\/[^\s"']+\/health\b/i)?.[0] || "";
}

function renderHistory() {
  const query = $("history-search").value.trim().toLowerCase();
  const filter = $("history-status").value;
  const filtered = state.incidents.filter((incident) => {
    const searchable = `${incident.service} ${incident.incident_id} ${incident.severity}`.toLowerCase();
    const category = incident.status === "archived" ? "archived" : incident.status === "resolved" ? "resolved" : isActiveIncident(incident) ? "active" : "other";
    return (!query || searchable.includes(query)) && (filter === "all" || filter === category);
  });
  $("history-list").innerHTML = filtered.length ? filtered.map((incident) => {
    const label = incident.status === "archived" ? "archived" : incident.status === "resolved" ? "resolved" : incident.approval_status.replaceAll("_", " ");
    const badgeClass = incident.status === "resolved" ? "executed" : incident.status === "archived" ? "rejected" : incident.approval_status;
    return `<button class="history-item ${state.incident?.incident_id === incident.incident_id ? "selected" : ""}" type="button" data-incident-id="${escapeHtml(incident.incident_id)}"><div><strong>${escapeHtml(incident.service)} · ${escapeHtml(incident.severity)}</strong><small>${escapeHtml(incident.incident_id)} · ${escapeHtml(incident.status)}</small></div><span class="status-badge ${badgeClass}">${escapeHtml(label)}</span></button>`;
  }).join("") : `<p class="muted history-empty">No matching incidents.</p>`;
}

function renderWorkflow() {
  const incident = state.incident || state.incidents.find(isActiveIncident) || null;
  const timeline = incident?.analysis?.timeline || [];
  $("workflow-context").textContent = incident ? `${incident.incident_id} · ${deriveWorkflowState(incident).label}` : "No active workflow";
  $("workflow-grid").innerHTML = workflowStages.map((stage) => {
    const event = timeline.find((item) => item.stage === stage);
    const status = event?.status || "pending";
    const detail = event?.detail || (incident ? "Waiting for this stage." : "Waiting for an active incident.");
    return `<div class="control-card"><span class="stage-status ${status}">${escapeHtml(status)}</span><strong>${escapeHtml(stage)}</strong><p>${escapeHtml(detail)}</p></div>`;
  }).join("");
  $("event-count").textContent = `${state.events.length} events`;
  $("event-list").innerHTML = state.events.length ? state.events.map((event) => `<button class="event-item" type="button" data-event-id="${escapeHtml(event.event_id)}"><strong>${escapeHtml(event.event_type)}</strong><small>${escapeHtml(new Date(event.occurred_at).toLocaleTimeString())}</small></button>`).join("") : `<p class="muted">No workflow events recorded yet.</p>`;
}

function renderSafety() {
  const runtime = state.runtime;
  if (!runtime) return;
  $("safety-runtime").textContent = `${String(runtime.mode).toUpperCase()} · ${String(runtime.environment).toUpperCase()}`;
  $("remediation-policy-state").textContent = runtime.live_remediation_enabled ? "LIVE" : "DISABLED";
  $("remediation-policy-state").classList.toggle("policy-disabled", !runtime.live_remediation_enabled);
}

function renderNodes() {
  const online = state.nodes.filter((node) => node.status === "online");
  $("nodes-context").textContent = online.length ? `${online.length} online` : "No registered Nodes";
  const formatSeen = (value) => value ? new Date(value).toLocaleString() : "No heartbeat";
  $("nodes-grid").innerHTML = state.nodes.length ? state.nodes.map((node) => `<article class="node-card"><div class="node-card-header"><div><strong>${escapeHtml(node.node_id)}</strong><p class="muted">${escapeHtml(node.hostname || "Unknown host")} · ${escapeHtml(node.platform)}</p></div><span class="node-status ${node.status === "offline" ? "offline" : ""}">${escapeHtml(node.status)}</span></div><div class="node-card-meta"><span>Last heartbeat<strong>${escapeHtml(formatSeen(node.last_seen))}</strong></span><span>Active incidents<strong>${node.active_incidents}</strong></span><span>Node version<strong>${escapeHtml(node.version)}</strong></span><span>Services<strong>${node.services.length}</strong></span></div><p class="node-services">${node.services.length ? `Monitored: ${escapeHtml(node.services.join(", "))}` : "No monitored services reported."}</p></article>`).join("") : `<div class="panel empty-view"><strong>No Nodes registered</strong><p class="muted">The Google Cloud control plane remains operational. SentinelOps Nodes appear here when they send a heartbeat.</p></div>`;
}

function applyRuntime() {
  const runtime = state.runtime;
  if (!runtime) return;
  $("mode-label").textContent = `${String(runtime.mode).toUpperCase()} · ${String(runtime.environment).toUpperCase()}`;
  $("footer-runtime").textContent = `${runtime.mode === "gemini" ? "Gemini / Vertex AI" : "Simulation"} · ${runtime.store} store · ${runtime.live_remediation_enabled ? "Live remediation allowlist enabled" : "Remediation executor disabled"}`;
  $("monitoring-title").textContent = runtime.pubsub_enabled ? "Monitoring configured sources" : "Detector publishing is disabled";
  $("monitoring-copy").textContent = runtime.pubsub_enabled ? "Cloud Logging and Pub/Sub signals will automatically create incidents here." : "Enable Pub/Sub delivery in deployment configuration to receive automatic detector events.";
  renderSafety();
}

function switchView(view) {
  state.view = view;
  document.querySelectorAll(".page-view").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  document.querySelectorAll(".nav-item").forEach((element) => element.classList.remove("active"));
  if (view === "incidents") $("incidents-nav").classList.add("active");
  if (view === "workflow") $("workflow-nav").classList.add("active");
  if (view === "safety") $("safety-nav").classList.add("active");
  const titles = { incidents: "Incident command center", workflow: "Workflow control plane", safety: "Safety policy", nodes: "SentinelOps Nodes" };
  $("view-title").textContent = titles[view] || titles.incidents;
  if (view === "workflow") renderWorkflow();
  if (view === "safety") renderSafety();
  if (view === "nodes") renderNodes();
}

async function loadIncident(incidentId, userSelected = true) {
  const incident = await requestJson(`/incidents/${encodeURIComponent(incidentId)}`);
  state.autoSelected = !userSelected;
  renderIncident(incident);
  renderHistory();
  switchView("incidents");
}

async function refreshLiveState() {
  try {
    const [incidents, runtime, nodes, events] = await Promise.all([
      requestJson("/incidents?limit=100"), requestJson("/settings"), requestJson("/nodes"), requestJson("/events?limit=25"),
    ]);
    state.incidents = incidents;
    state.runtime = runtime;
    state.nodes = nodes;
    state.events = events;
    applyRuntime(); updateMetrics(); renderHistory(); renderWorkflow(); renderNodes();
    const active = incidents.filter(isActiveIncident);
    if (active.length && (state.autoSelected || !state.incident || !incidents.some((item) => item.incident_id === state.incident.incident_id))) {
      state.autoSelected = true;
      renderIncident(active[0]);
    } else if (!active.length && state.autoSelected) {
      clearIncident();
    } else if (state.incident) {
      const refreshed = incidents.find((item) => item.incident_id === state.incident.incident_id);
      if (refreshed) renderIncident(refreshed);
    }
    const online = nodes.filter((node) => node.status === "online");
    $("node-card-title").textContent = online.length ? `${online.length} Node${online.length === 1 ? "" : "s"} online` : "Cloud control plane";
    $("node-card-status").textContent = online.length ? online.map((node) => `${node.node_id} · ${node.platform}`).join(" · ") : `${runtime.mode} · ${runtime.store} · ${runtime.environment}`;
    $("last-updated").textContent = `Live · updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
    $("last-updated").classList.remove("stale");
  } catch (error) {
    $("last-updated").textContent = "Live refresh unavailable";
    $("last-updated").classList.add("stale");
    console.error(error);
  }
}

async function createIncident(service, severity, summary) {
  const incident = await requestJson("/incidents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ service, severity, summary, source: "manual" }) });
  state.autoSelected = false;
  renderIncident(incident);
  $("manual-panel").classList.add("hidden");
  await refreshLiveState();
}

async function decide(decision) {
  if (!state.incident) return;
  const updated = await requestJson(`/incidents/${state.incident.incident_id}/approval`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, comment: $("approval-comment").value }) });
  $("approval-comment").value = "";
  renderIncident(updated);
  await refreshLiveState();
}

async function executeRemediation() {
  if (!state.incident) return;
  const targetRevision = $("target-revision").value.trim() || inferTargetRevision(state.incident);
  const region = $("target-region").value.trim() || "europe-west1";
  if (!targetRevision) throw new Error("Enter the explicit healthy Cloud Run target revision before executing rollback");
  if (!window.confirm(`Execute approved rollback?\n\nService: ${state.incident.service}\nTarget revision: ${targetRevision}\nRegion: ${region}\n\nThis changes live Cloud Run traffic.`)) return;
  const updated = await requestJson(`/incidents/${state.incident.incident_id}/execute`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true, action: "cloud_run_rollback", target_revision: targetRevision, region }) });
  renderIncident(updated);
  await refreshLiveState();
}

async function verifyRemediation() {
  if (!state.incident) return;
  const healthUrl = deriveHealthUrl(state.incident);
  if (!healthUrl) throw new Error("No real health endpoint was found in incident evidence");
  const updated = await requestJson(`/incidents/${state.incident.incident_id}/verify/health`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: healthUrl, expected_status: 200, timeout_seconds: 5 }) });
  renderIncident(updated);
  await refreshLiveState();
}

const settings = {
  open: async () => {
    $("settings-backdrop").classList.remove("hidden");
    $("settings-backdrop").setAttribute("aria-hidden", "false");
    await settings.load();
    $("settings-close").focus();
  },
  close: () => { $("settings-backdrop").classList.add("hidden"); $("settings-backdrop").setAttribute("aria-hidden", "true"); },
  load: async () => {
    const payload = await requestJson("/settings");
    $("settings-mode").value = payload.mode; $("settings-model").value = payload.model; $("settings-store").value = payload.store;
    $("settings-environment").value = payload.environment; $("settings-project").value = payload.project; $("settings-location").value = payload.location;
    $("settings-topic").value = payload.pubsub_topic; $("settings-subscription").value = payload.pubsub_subscription || ""; $("settings-firestore-database").value = payload.firestore_database || "(default)"; $("settings-pubsub").checked = payload.pubsub_enabled;
    const production = payload.environment === "production";
    document.querySelectorAll("#settings-form input, #settings-form select").forEach((control) => { control.disabled = production; });
    $("settings-save").disabled = production;
    $("settings-intro").textContent = production ? "Cloud Run runtime configuration is read-only here. Change deployment environment variables and redeploy to make durable production changes." : "Manage non-secret local runtime configuration. Changes apply after restarting the API.";
    $("settings-runtime").textContent = `${payload.mode.toUpperCase()} · Vertex AI ADC · ${payload.store} · ${payload.environment}`;
  },
  save: async (event) => {
    event.preventDefault();
    const status = $("settings-status"); status.className = "settings-status"; status.textContent = "Saving configuration…"; status.classList.remove("hidden");
    try {
      const payload = await requestJson("/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: $("settings-mode").value, model: $("settings-model").value, store: $("settings-store").value, environment: $("settings-environment").value, project: $("settings-project").value, location: $("settings-location").value, pubsub_topic: $("settings-topic").value, pubsub_subscription: $("settings-subscription").value, firestore_database: $("settings-firestore-database").value, pubsub_enabled: $("settings-pubsub").checked }) });
      status.textContent = "Configuration saved. Restart the API to apply backend changes.";
      $("settings-runtime").textContent = `${payload.mode.toUpperCase()} · restart required · ${payload.save_target}`;
    } catch (error) { status.className = "settings-status error"; status.textContent = error.message || "Settings save failed"; }
  },
};

function setupSidebar() {
  const sidebar = $("sidebar"); const toggle = $("sidebar-toggle"); const shell = document.querySelector(".shell");
  const saved = localStorage.getItem("sentinelops.sidebarCollapsed") === "true";
  const apply = (collapsed) => { sidebar.classList.toggle("collapsed", collapsed); shell.classList.toggle("sidebar-collapsed", collapsed); toggle.setAttribute("aria-expanded", String(!collapsed)); toggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar"); toggle.querySelector("img").src = `/dashboard-assets/sheet/${collapsed ? "sidebar-expand" : "sidebar-collapse"}.png?v=20260820-2`; };
  apply(saved);
  toggle.addEventListener("click", () => { const collapsed = !sidebar.classList.contains("collapsed"); apply(collapsed); localStorage.setItem("sentinelops.sidebarCollapsed", String(collapsed)); });
}

setupSidebar();
$("incidents-nav").addEventListener("click", (event) => { event.preventDefault(); switchView("incidents"); });
$("workflow-nav").addEventListener("click", (event) => { event.preventDefault(); switchView("workflow"); });
$("safety-nav").addEventListener("click", (event) => { event.preventDefault(); switchView("safety"); });
$("node-card").addEventListener("click", () => switchView("nodes"));
$("node-card").addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); switchView("nodes"); } });
$("manual-toggle").addEventListener("click", () => { $("manual-panel").classList.remove("hidden"); $("service").focus(); });
$("manual-close").addEventListener("click", () => $("manual-panel").classList.add("hidden"));
$("demo-button").addEventListener("click", () => { $("service").value = "demo-api"; $("severity").value = "high"; $("summary").value = "HTTP 500 rate exceeded after latest deployment"; $("summary").focus(); });
$("incident-form").addEventListener("submit", async (event) => { event.preventDefault(); setError(""); try { await createIncident($("service").value, $("severity").value, $("summary").value); } catch (error) { setError(error.message); } });
$("history-search").addEventListener("input", renderHistory); $("history-status").addEventListener("change", renderHistory);
$("history-list").addEventListener("click", (event) => { const target = event.target.closest("[data-incident-id]"); if (target) loadIncident(target.dataset.incidentId, true).catch((error) => setError(error.message)); });
$("event-list").addEventListener("click", (event) => { const target = event.target.closest("[data-event-id]"); if (!target) return; const record = state.events.find((item) => item.event_id === target.dataset.eventId); if (!record) return; $("event-detail").classList.remove("hidden"); $("event-detail").innerHTML = `<strong>${escapeHtml(record.event_type)} · ${escapeHtml(record.event_id)}</strong><pre>${escapeHtml(JSON.stringify(record.payload, null, 2))}</pre>`; });
$("approve-button").addEventListener("click", () => decide("approve").catch((error) => setError(error.message)));
$("reject-button").addEventListener("click", () => decide("reject").catch((error) => setError(error.message)));
$("execute-button").addEventListener("click", () => executeRemediation().catch((error) => setError(error.message)));
$("verify-button").addEventListener("click", () => verifyRemediation().catch((error) => setError(error.message)));
$("settings-button").addEventListener("click", () => settings.open().catch((error) => console.error(error)));
$("settings-close").addEventListener("click", settings.close); $("settings-cancel").addEventListener("click", settings.close); $("settings-form").addEventListener("submit", settings.save);
$("settings-backdrop").addEventListener("click", (event) => { if (event.target === $("settings-backdrop")) settings.close(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("settings-backdrop").classList.contains("hidden")) settings.close(); });

switchView("incidents");
refreshLiveState();
window.setInterval(refreshLiveState, 8000);
