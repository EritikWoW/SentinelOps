(() => {
  const $ = (id) => document.getElementById(id);

  function setLiveSafetyCopy() {
    const body = $("control-body");
    if (!body || $("control-eyebrow")?.textContent !== "SAFETY POLICY") return;
    body.innerHTML = `<div class="policy-list"><div class="policy-row"><img src="/dashboard-assets/sheet/shield-check.png" alt="" /><div><strong>Human approval required</strong><p>High-risk actions remain blocked until an operator approves the proposed remediation.</p></div><span class="locked-pill">LOCKED</span></div><div class="policy-row"><img src="/dashboard-assets/sheet/refresh.png" alt="" /><div><strong>Allowlisted live remediation</strong><p>Approved actions may change configured Cloud Run services. Targets remain constrained by the remediation allowlist.</p></div><span class="locked-pill">LIVE</span></div><div class="policy-row"><img src="/dashboard-assets/sheet/heartbeat.png" alt="" /><div><strong>Verification required</strong><p>Executed remediation is not considered resolved until a real health check passes.</p></div><span class="locked-pill">ON</span></div></div>`;
  }

  async function refreshRuntimePresentation() {
    try {
      const response = await fetch("/settings", { cache: "no-store" });
      if (!response.ok) return;
      const runtime = await response.json();
      const mode = String(runtime.mode || "unknown").toUpperCase();
      const environment = String(runtime.environment || "unknown").toUpperCase();
      const modeLabel = $("mode-label");
      if (modeLabel) modeLabel.textContent = `${mode} · ${environment}`;

      const footerRuntime = $("footer-runtime");
      if (footerRuntime) {
        footerRuntime.textContent = runtime.mode === "gemini"
          ? "Live Cloud Run remediation enabled · Approval + verification required"
          : "Simulation mode active · Infrastructure mutation disabled";
      }
    } catch (_) {
      // Keep the static production-safe copy when runtime settings are temporarily unavailable.
    }
  }

  const nodeTitle = $("node-card-title");
  const nodeStatus = $("node-card-status");
  if (nodeTitle) {
    const observer = new MutationObserver(() => {
      if (nodeTitle.textContent === "Demo environment") nodeTitle.textContent = "Cloud control plane";
    });
    observer.observe(nodeTitle, { childList: true, characterData: true, subtree: true });
    if (nodeTitle.textContent === "Demo environment") nodeTitle.textContent = "Cloud control plane";
  }
  if (nodeStatus && nodeStatus.textContent === "Local control plane") nodeStatus.textContent = "Production runtime";

  $("safety-nav")?.addEventListener("click", () => window.setTimeout(setLiveSafetyCopy, 0));
  refreshRuntimePresentation();
  window.setInterval(refreshRuntimePresentation, 15000);
})();
