(() => {
  const $ = (id) => document.getElementById(id);
  const workflowStages = ["detect", "investigate", "decide", "remediate", "verify", "report"];
  let autoSelectedIncidentId = null;
  let runtimeSnapshot = null;

  function showError(message) {
    if (typeof window.setError === "function") {
      window.setError(message || "");
      return;
    }
    const element = $("form-error");
    if (!element) return;
    element.textContent = message || "";
    element.classList.toggle("hidden", !message);
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    return payload;
  }

  function deriveWorkflowState(incident) {
    if (!incident) return { label: "WAITING", state: "waiting" };
    const analysis = incident.analysis || {};
    const timeline = analysis.timeline || [];
    const completed = new Set(timeline.filter((item) => item.status === "completed").map((item) => item.stage));

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

  function updateIncidentPresentation(incident) {
    const workflow = deriveWorkflowState(incident);
    const workflowBadge = $("workflow-state");
    if (workflowBadge) {
      workflowBadge.textContent = workflow.label;
      workflowBadge.className = `workflow-state ${workflow.state}`;
    }

    const reportEvent = incident?.analysis?.timeline?.find((item) => item.stage === "report" && item.status === "completed");
    const reportSection = $("report-section");
    if (reportSection) reportSection.classList.toggle("hidden", !reportEvent);
    if ($("report-detail")) $("report-detail").textContent = reportEvent?.detail || "";
    if ($("report-status")) {
      $("report-status").textContent = incident?.status === "resolved" ? "RESOLVED" : "FINAL";
      $("report-status").className = `report-status ${incident?.status === "resolved" ? "resolved" : ""}`;
    }
  }

  function render(incident) {
    if (!incident) return;
    if (typeof window.renderIncident === "function") window.renderIncident(incident);
    syncActionControls(incident);
    updateIncidentPresentation(incident);
  }

  function completedStages(incident) {
    const timeline = incident?.analysis?.timeline || [];
    return new Set(timeline.filter((item) => item.status === "completed").map((item) => item.stage)).size;
  }

  function isActiveIncident(incident) {
    return !["resolved", "remediation_failed"].includes(incident.status);
  }

  function setMetricState(elementId, state) {
    const element = $(elementId)?.closest(".metric-card");
    if (element) element.dataset.state = state;
  }

  function updateMetricsFromData(incidents, runtime) {
    const active = incidents.filter(isActiveIncident);
    const latest = active[0] || incidents[0] || null;

    if ($("metric-active")) $("metric-active").textContent = String(active.length).padStart(2, "0");
    if ($("metric-active-foot")) {
      $("metric-active-foot").textContent = active.length
        ? `● ${active.filter((item) => item.approval_status === "pending").length} awaiting approval`
        : "● No unresolved incidents";
    }
    setMetricState("metric-active", active.length ? "attention" : "ok");

    const completed = completedStages(latest);
    if ($("metric-workflow")) $("metric-workflow").textContent = latest ? `${completed}/6` : "0/6";
    if ($("metric-workflow-foot")) {
      const state = deriveWorkflowState(latest);
      $("metric-workflow-foot").textContent = latest
        ? `${latest.service} · ${state.label.toLowerCase()}`
        : "No workflow currently recorded";
    }
    setMetricState("metric-workflow", latest && latest.status === "remediation_failed" ? "danger" : "ok");

    const live = runtime?.mode === "gemini";
    if ($("metric-policy")) $("metric-policy").textContent = live ? "SAFE" : "SIM";
    if ($("metric-policy-foot")) {
      $("metric-policy-foot").textContent = live
        ? "● Approval + allowlist + verification"
        : "● Simulation mode active";
    }
    setMetricState("metric-policy", "ok");
  }

  function maybeAutoRenderLatest(incidents) {
    const latest = incidents[0];
    if (!latest) return;
    const displayed = $("incident-id")?.textContent?.trim() || "";
    if (!displayed || displayed === autoSelectedIncidentId) {
      render(latest);
      autoSelectedIncidentId = latest.incident_id;
    } else if (displayed === latest.incident_id) {
      render(latest);
    }
  }

  function setLiveSafetyCopy() {
    const body = $("control-body");
    if (!body || $("control-eyebrow")?.textContent !== "SAFETY POLICY") return;
    body.innerHTML = `<div class="policy-list"><div class="policy-row"><img src="/dashboard-assets/sheet/shield-check.png" alt="" /><div><strong>Human approval required</strong><p>High-risk actions remain blocked until an operator approves the proposed remediation.</p></div><span class="locked-pill">LOCKED</span></div><div class="policy-row"><img src="/dashboard-assets/sheet/refresh.png" alt="" /><div><strong>Allowlisted live remediation</strong><p>Approved Cloud Run rollback actions are limited to configured services and an explicit target revision.</p></div><span class="locked-pill">LIVE</span></div><div class="policy-row"><img src="/dashboard-assets/sheet/heartbeat.png" alt="" /><div><strong>Real verification required</strong><p>A remediation is not resolved until the configured health endpoint returns HTTP 200.</p></div><span class="locked-pill">ON</span></div></div>`;
  }

  function applyRuntime(runtime) {
    runtimeSnapshot = runtime;
    const mode = String(runtime.mode || "unknown").toUpperCase();
    const environment = String(runtime.environment || "unknown").toUpperCase();
    if ($("mode-label")) $("mode-label").textContent = `${mode} · ${environment}`;
    if ($("footer-runtime")) {
      $("footer-runtime").textContent = runtime.mode === "gemini"
        ? `Gemini / Vertex AI · ${runtime.store} store · Approval + verification required`
        : "Simulation mode active · Infrastructure mutation disabled";
    }
  }

  function markRefreshSuccess() {
    const element = $("last-updated");
    if (!element) return;
    element.textContent = `Live · updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
    element.classList.remove("stale");
  }

  function markRefreshFailure() {
    const element = $("last-updated");
    if (!element) return;
    element.textContent = "Live refresh unavailable";
    element.classList.add("stale");
  }

  async function refreshLiveState() {
    try {
      const [incidents, runtime, nodes] = await Promise.all([
        requestJson("/incidents?limit=25"),
        requestJson("/settings"),
        requestJson("/nodes"),
      ]);
      applyRuntime(runtime);
      updateMetricsFromData(incidents, runtime);
      maybeAutoRenderLatest(incidents);

      const online = nodes.filter((node) => node.status === "online");
      if ($("node-card-title")) {
        $("node-card-title").textContent = online.length
          ? `${online.length} Node${online.length === 1 ? "" : "s"} online`
          : "Cloud control plane";
      }
      if ($("node-card-status")) {
        $("node-card-status").textContent = online.length
          ? online.map((node) => `${node.node_id} · ${node.platform}`).join(" · ")
          : `${runtime.mode} · ${runtime.store} · ${runtime.environment}`;
      }
      markRefreshSuccess();
    } catch (_) {
      if ($("metric-active-foot")) $("metric-active-foot").textContent = "● Runtime refresh unavailable";
      markRefreshFailure();
    }
  }

  function escapedServicePattern(service) {
    return String(service || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function inferTargetRevision(incident) {
    const service = escapedServicePattern(incident?.service);
    if (!service) return "";
    const pattern = new RegExp(`${service}-\\d{5}-[a-z0-9]+`, "gi");
    const preferredText = [
      incident?.analysis?.execution_notes || "",
      incident?.analysis?.remediation_action || "",
    ].join(" ");
    const preferred = preferredText.match(pattern) || [];
    const failing = new Set((incident?.evidence || []).flatMap((item) => String(item).match(pattern) || []));
    return preferred.find((revision) => !failing.has(revision)) || preferred[0] || "";
  }

  function syncActionControls(incident) {
    const analysis = incident?.analysis || {};
    const approved = incident?.approval_status === "approved";
    const executed = analysis.remediation_status === "executed";
    const targets = $("execution-targets");
    if (targets) targets.classList.toggle("hidden", !approved || executed);

    const target = $("target-revision");
    if (target && approved && !target.value) target.value = inferTargetRevision(incident);
    if ($("target-region") && !$("target-region").value) $("target-region").value = "europe-west1";
  }

  async function currentIncident() {
    const id = $("incident-id")?.textContent?.trim();
    if (!id) throw new Error("Select an incident first");
    return requestJson(`/incidents/${encodeURIComponent(id)}`);
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
    const summaryMatch = String(incident?.summary || "").match(/https?:\/\/[^\s"']+\/health\b/i);
    return summaryMatch ? summaryMatch[0] : "";
  }

  async function executeLiveRemediation(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    showError("");
    try {
      const incident = await currentIncident();
      if (incident.approval_status !== "approved") throw new Error("Human approval is required before execution");
      const targetRevision = $("target-revision")?.value.trim() || inferTargetRevision(incident);
      const region = $("target-region")?.value.trim() || "europe-west1";
      if (!targetRevision) throw new Error("Enter the explicit healthy Cloud Run target revision before executing rollback");

      const confirmed = window.confirm(
        `Execute approved rollback?\n\nService: ${incident.service}\nTarget revision: ${targetRevision}\nRegion: ${region}\n\nThis will change live Cloud Run traffic.`
      );
      if (!confirmed) return;

      const updated = await requestJson(`/incidents/${encodeURIComponent(incident.incident_id)}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirm: true,
          action: "cloud_run_rollback",
          target_revision: targetRevision,
          region,
        }),
      });
      render(updated);
      autoSelectedIncidentId = updated.incident_id;
      await refreshLiveState();
    } catch (error) {
      showError(error.message || "Live remediation failed");
    }
  }

  async function verifyLiveRemediation(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    showError("");
    try {
      const incident = await currentIncident();
      if (incident?.analysis?.remediation_status !== "executed") throw new Error("Execute remediation before verification");
      const healthUrl = deriveHealthUrl(incident);
      if (!healthUrl) throw new Error("No real health endpoint was found in incident evidence; verification cannot be marked successful manually");
      const updated = await requestJson(`/incidents/${encodeURIComponent(incident.incident_id)}/verify/health`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: healthUrl, expected_status: 200, timeout_seconds: 5 }),
      });
      render(updated);
      autoSelectedIncidentId = updated.incident_id;
      await refreshLiveState();
    } catch (error) {
      showError(error.message || "Health verification failed");
    }
  }

  function loadTestScenario(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    $("service").value = "demo-api";
    $("severity").value = "high";
    $("summary").value = "HTTP 500 rate exceeded after latest deployment";
    showError("");
    $("summary").focus();
  }

  async function configureSettingsForRuntime() {
    try {
      const runtime = runtimeSnapshot || await requestJson("/settings");
      const production = runtime.environment === "production";
      const controls = document.querySelectorAll("#settings-form input, #settings-form select");
      controls.forEach((control) => { control.disabled = production; });
      const save = $("settings-save");
      if (save) save.disabled = production;
      if ($("settings-intro")) {
        $("settings-intro").textContent = production
          ? "Cloud Run runtime configuration is read-only here. Change deployment environment variables and redeploy to make durable production changes."
          : "Manage non-secret local runtime configuration. Changes apply after restarting the API.";
      }
      if ($("settings-runtime")) {
        $("settings-runtime").textContent = `${String(runtime.mode).toUpperCase()} · Vertex AI ADC · ${runtime.store} · ${runtime.environment}`;
      }
    } catch (_) {
      // The base settings dialog remains usable if runtime inspection fails.
    }
  }

  function setupSidebar() {
    const sidebar = $("sidebar");
    const toggle = $("sidebar-toggle");
    if (!sidebar || !toggle) return;
    const shell = document.querySelector(".shell");
    const savedValue = localStorage.getItem("sentinelops.sidebarCollapsed");
    const saved = savedValue === null
      ? localStorage.getItem("sentinelops.sidebar.collapsed") === "true"
      : savedValue === "true";
    shell.classList.toggle("sidebar-collapsed", saved);
    sidebar.classList.toggle("collapsed", saved);
    toggle.setAttribute("aria-expanded", String(!saved));
    toggle.setAttribute("aria-label", saved ? "Expand sidebar" : "Collapse sidebar");
    toggle.querySelector("img").src = `/dashboard-assets/sheet/${saved ? "sidebar-expand" : "sidebar-collapse"}.png?v=20260820-2`;
    toggle.addEventListener("click", () => {
      const collapsed = sidebar.classList.toggle("collapsed");
      shell.classList.toggle("sidebar-collapsed", collapsed);
      toggle.setAttribute("aria-expanded", String(!collapsed));
      toggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
      toggle.querySelector("img").src = `/dashboard-assets/sheet/${collapsed ? "sidebar-expand" : "sidebar-collapse"}.png?v=20260820-2`;
      localStorage.setItem("sentinelops.sidebarCollapsed", String(collapsed));
      localStorage.setItem("sentinelops.sidebar.collapsed", String(collapsed));
    });
  }

  setupSidebar();
  $("safety-nav")?.addEventListener("click", () => window.setTimeout(setLiveSafetyCopy, 0));
  $("settings-button")?.addEventListener("click", () => window.setTimeout(configureSettingsForRuntime, 0));
  $("demo-button")?.addEventListener("click", loadTestScenario, true);
  $("execute-button")?.addEventListener("click", executeLiveRemediation, true);
  $("verify-button")?.addEventListener("click", verifyLiveRemediation, true);

  const incidentId = $("incident-id");
  if (incidentId) new MutationObserver(() => window.setTimeout(async () => {
    try {
      const incident = await currentIncident();
      syncActionControls(incident);
      updateIncidentPresentation(incident);
    } catch (_) { /* no incident selected */ }
  }, 0)).observe(incidentId, { childList: true, characterData: true, subtree: true });

  refreshLiveState();
  window.setInterval(refreshLiveState, 8000);
})();
