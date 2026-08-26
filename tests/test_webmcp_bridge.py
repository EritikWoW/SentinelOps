import json
import shutil
import subprocess
from pathlib import Path

import pytest


WEB_DIR = Path(__file__).resolve().parents[1] / "src" / "web"
WEBMCP_SOURCE = WEB_DIR / "assets" / "webmcp.js"


def test_dashboard_loads_webmcp_bridge() -> None:
    html = (WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    assert "/dashboard-assets/webmcp.js" in html


def test_webmcp_bridge_exposes_bounded_incident_tools() -> None:
    source = WEBMCP_SOURCE.read_text(encoding="utf-8")
    expected_tools = {
        "sentinelops_list_incidents",
        "sentinelops_get_incident",
        "sentinelops_list_events",
        "sentinelops_list_nodes",
        "sentinelops_approve_remediation",
        "sentinelops_reject_remediation",
        "sentinelops_execute_remediation",
        "sentinelops_verify_recovery",
    }
    for tool_name in expected_tools:
        assert f'name: "{tool_name}"' in source


def test_webmcp_keeps_existing_safety_gates() -> None:
    source = WEBMCP_SOURCE.read_text(encoding="utf-8")
    assert 'incident.approval_status !== "approved"' in source
    assert 'confirmation !== "EXECUTE_APPROVED_REMEDIATION"' in source
    assert '/verify/health' in source
    assert 'remediation_status === "blocked"' in source


def _run_webmcp_harness(scenario: str) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the WebMCP browser-bridge runtime harness")

    script = r'''
const fs = require("fs");
const vm = require("vm");
const sourcePath = process.argv[1];
const scenario = process.argv[2];
const source = fs.readFileSync(sourcePath, "utf8");

const registered = [];
const fetchCalls = [];
const listeners = {};

function element() {
  return {
    id: "",
    className: "",
    textContent: "",
    title: "",
    dataset: {},
    appendChild() {},
  };
}

const badgeHost = element();
const document = {
  readyState: "complete",
  modelContext: {
    registerTool(tool) {
      registered.push(tool);
      return Promise.resolve();
    },
  },
  getElementById() { return null; },
  querySelector(selector) { return selector === ".monitoring-badges" ? badgeHost : null; },
  createElement() { return element(); },
  addEventListener() {},
};

const window = {
  dispatchEvent() {},
};

class CustomEvent {
  constructor(type, init = {}) { this.type = type; this.detail = init.detail; }
}

class Headers {
  constructor(initial = {}) { this.values = { ...initial }; }
  has(name) { return Object.keys(this.values).some((key) => key.toLowerCase() === name.toLowerCase()); }
  set(name, value) { this.values[name] = value; }
}

const responses = [];
function queueResponse(status, payload) { responses.push({ status, payload }); }

async function fetch(url, options = {}) {
  fetchCalls.push({ url: String(url), method: options.method || "GET", body: options.body || null });
  const next = responses.shift();
  if (!next) throw new Error(`No mocked response queued for ${url}`);
  return {
    ok: next.status >= 200 && next.status < 300,
    status: next.status,
    statusText: next.status === 200 ? "OK" : "ERROR",
    async json() { return next.payload; },
  };
}

const context = {
  console,
  document,
  navigator: {},
  window,
  CustomEvent,
  Headers,
  fetch,
  setTimeout,
  clearTimeout,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: sourcePath });

(async () => {
  await new Promise((resolve) => setImmediate(resolve));
  const tools = Object.fromEntries(registered.map((tool) => [tool.name, tool]));
  const names = registered.map((tool) => tool.name);

  if (scenario === "registration") {
    process.stdout.write(JSON.stringify({ names, available: window.SentinelOpsWebMCP?.available }));
    return;
  }

  if (scenario === "read") {
    queueResponse(200, [{ incident_id: "inc-1", status: "investigating" }]);
    const result = JSON.parse(await tools.sentinelops_list_incidents.execute({ limit: 500 }));
    process.stdout.write(JSON.stringify({ result, calls: fetchCalls }));
    return;
  }

  if (scenario === "approval") {
    queueResponse(200, { incident_id: "inc-1", approval_status: "pending" });
    queueResponse(200, { incident_id: "inc-1", approval_status: "approved" });
    const result = JSON.parse(await tools.sentinelops_approve_remediation.execute({ incident_id: "inc-1", comment: "approved by test" }));
    process.stdout.write(JSON.stringify({ result, calls: fetchCalls }));
    return;
  }

  if (scenario === "execute_without_approval") {
    queueResponse(200, { incident_id: "inc-1", approval_status: "pending", analysis: { remediation_status: "planned" } });
    let error = null;
    try {
      await tools.sentinelops_execute_remediation.execute({
        incident_id: "inc-1",
        target_revision: "demo-api-00001-good",
        confirmation: "EXECUTE_APPROVED_REMEDIATION",
      });
    } catch (exc) { error = exc.message; }
    process.stdout.write(JSON.stringify({ error, calls: fetchCalls }));
    return;
  }

  if (scenario === "execute_without_confirmation") {
    let error = null;
    try {
      await tools.sentinelops_execute_remediation.execute({
        incident_id: "inc-1",
        target_revision: "demo-api-00001-good",
        confirmation: "NO",
      });
    } catch (exc) { error = exc.message; }
    process.stdout.write(JSON.stringify({ error, calls: fetchCalls }));
    return;
  }

  if (scenario === "execute_approved") {
    queueResponse(200, { incident_id: "inc-1", approval_status: "approved", analysis: { remediation_status: "planned" } });
    queueResponse(200, { incident_id: "inc-1", approval_status: "approved", analysis: { remediation_status: "executed" } });
    const result = JSON.parse(await tools.sentinelops_execute_remediation.execute({
      incident_id: "inc-1",
      target_revision: "demo-api-00001-good",
      region: "europe-west1",
      confirmation: "EXECUTE_APPROVED_REMEDIATION",
    }));
    process.stdout.write(JSON.stringify({ result, calls: fetchCalls }));
    return;
  }

  if (scenario === "verify_before_execute") {
    queueResponse(200, { incident_id: "inc-1", analysis: { remediation_status: "planned" } });
    let error = null;
    try {
      await tools.sentinelops_verify_recovery.execute({ incident_id: "inc-1", health_url: "https://example.test/health" });
    } catch (exc) { error = exc.message; }
    process.stdout.write(JSON.stringify({ error, calls: fetchCalls }));
    return;
  }

  throw new Error(`Unknown scenario: ${scenario}`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
'''
    completed = subprocess.run(
        [node, "-e", script, str(WEBMCP_SOURCE), scenario],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_webmcp_runtime_registers_exact_bounded_tool_set() -> None:
    result = _run_webmcp_harness("registration")
    assert result["available"] is True
    assert set(result["names"]) == {
        "sentinelops_list_incidents",
        "sentinelops_get_incident",
        "sentinelops_list_events",
        "sentinelops_list_nodes",
        "sentinelops_approve_remediation",
        "sentinelops_reject_remediation",
        "sentinelops_execute_remediation",
        "sentinelops_verify_recovery",
    }
    assert len(result["names"]) == 8


def test_webmcp_read_tool_executes_and_bounds_limit() -> None:
    result = _run_webmcp_harness("read")
    assert result["result"]["count"] == 1
    assert result["calls"] == [{"url": "/incidents?limit=100", "method": "GET", "body": None}]


def test_webmcp_approval_uses_existing_backend_gate() -> None:
    result = _run_webmcp_harness("approval")
    assert result["result"]["approval_status"] == "approved"
    assert result["calls"][0]["url"] == "/incidents/inc-1"
    assert result["calls"][1]["url"] == "/incidents/inc-1/approval"
    assert result["calls"][1]["method"] == "POST"
    assert json.loads(result["calls"][1]["body"]) == {"decision": "approve", "comment": "approved by test"}


def test_webmcp_execute_refuses_unapproved_incident_without_posting() -> None:
    result = _run_webmcp_harness("execute_without_approval")
    assert "Human approval is required" in result["error"]
    assert len(result["calls"]) == 1
    assert result["calls"][0]["method"] == "GET"


def test_webmcp_execute_requires_explicit_confirmation_before_any_request() -> None:
    result = _run_webmcp_harness("execute_without_confirmation")
    assert "Explicit WebMCP execution confirmation is required" in result["error"]
    assert result["calls"] == []


def test_webmcp_execute_approved_calls_existing_execute_endpoint() -> None:
    result = _run_webmcp_harness("execute_approved")
    assert result["result"]["analysis"]["remediation_status"] == "executed"
    assert result["calls"][1]["url"] == "/incidents/inc-1/execute"
    assert result["calls"][1]["method"] == "POST"
    assert json.loads(result["calls"][1]["body"]) == {
        "confirm": True,
        "action": "cloud_run_rollback",
        "target_revision": "demo-api-00001-good",
        "region": "europe-west1",
    }


def test_webmcp_verification_refuses_before_execution() -> None:
    result = _run_webmcp_harness("verify_before_execute")
    assert "Remediation must be executed" in result["error"]
    assert len(result["calls"]) == 1
    assert result["calls"][0]["method"] == "GET"
