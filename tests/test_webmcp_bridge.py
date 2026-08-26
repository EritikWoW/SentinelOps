from pathlib import Path


WEB_DIR = Path(__file__).resolve().parents[1] / "src" / "web"


def test_dashboard_loads_webmcp_bridge() -> None:
    html = (WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    assert "/dashboard-assets/webmcp.js" in html


def test_webmcp_bridge_exposes_bounded_incident_tools() -> None:
    source = (WEB_DIR / "assets" / "webmcp.js").read_text(encoding="utf-8")
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
    source = (WEB_DIR / "assets" / "webmcp.js").read_text(encoding="utf-8")
    assert 'incident.approval_status !== "approved"' in source
    assert 'confirmation !== "EXECUTE_APPROVED_REMEDIATION"' in source
    assert '/verify/health' in source
    assert 'remediation_status === "blocked"' in source
