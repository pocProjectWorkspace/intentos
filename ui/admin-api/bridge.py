"""
Python-Node Bridge for IntentOS Admin Console

Runs alongside the Express API. Express forwards requests here
to get real data from Python modules.

Usage: python bridge.py  (listens on port 7892)
"""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.inference.hardware import HardwareDetector
from core.enterprise.auth import AuthManager, AuthProvider
from core.enterprise.siem import SIEMExporter, AuditEvent
from core.enterprise.compliance import ComplianceReporter, ComplianceFramework
from core.enterprise.workspaces import WorkspaceManager as TeamWorkspaceManager
from core.security.sandbox import SandboxPolicy
from core.orchestration.cost_manager import CostManager

# ---------------------------------------------------------------------------
# Singleton instances (initialized once on startup)
# ---------------------------------------------------------------------------

hardware_detector = HardwareDetector()
auth_manager = AuthManager()
siem_exporter = SIEMExporter()
compliance_reporter = ComplianceReporter()
workspace_manager = TeamWorkspaceManager()
cost_manager = CostManager(budget=100.0)

# Seed some demo data so the bridge returns useful results out of the box

# -- Auth: register a few API key users ------------------------------------
_demo_users = [
    ("u-001", "admin"),
    ("u-002", "alice"),
    ("u-003", "bob"),
]
_demo_api_keys = {}
for uid, uname in _demo_users:
    key = auth_manager.register_api_key(uid, uname)
    _demo_api_keys[uname] = key

# -- Audit events ----------------------------------------------------------
_demo_audit_events = [
    AuditEvent(
        timestamp=datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc),
        event_id="evt-001",
        event_type="audit_log_entry",
        severity="info",
        agent="agent-alpha",
        action="login",
        user="admin",
        paths_accessed=[],
        result="success",
        duration_ms=42,
        details={"ip": "10.0.0.1"},
    ),
    AuditEvent(
        timestamp=datetime(2026, 3, 28, 10, 5, 0, tzinfo=timezone.utc),
        event_id="evt-002",
        event_type="sandbox_enforcement",
        severity="warning",
        agent="agent-beta",
        action="policy_violation",
        user="alice",
        paths_accessed=["/etc/passwd"],
        result="blocked",
        duration_ms=3,
        details={"path": "/etc/passwd"},
    ),
    AuditEvent(
        timestamp=datetime(2026, 3, 28, 10, 10, 0, tzinfo=timezone.utc),
        event_id="evt-003",
        event_type="sandbox_enforcement",
        severity="error",
        agent="agent-alpha",
        action="sandbox_escape",
        user="bob",
        paths_accessed=["~/.ssh/id_rsa"],
        result="blocked",
        duration_ms=1,
        details={"path": "~/.ssh/id_rsa"},
    ),
    AuditEvent(
        timestamp=datetime(2026, 3, 28, 10, 15, 0, tzinfo=timezone.utc),
        event_id="evt-004",
        event_type="audit_log_entry",
        severity="info",
        agent="agent-gamma",
        action="deployment",
        user="admin",
        paths_accessed=[],
        result="success",
        duration_ms=1200,
        details={"model": "llama-3.1-70b", "target": "workstation-1"},
    ),
    AuditEvent(
        timestamp=datetime(2026, 3, 28, 10, 20, 0, tzinfo=timezone.utc),
        event_id="evt-005",
        event_type="access_grant",
        severity="info",
        agent="agent-beta",
        action="login",
        user="alice",
        paths_accessed=[],
        result="success",
        duration_ms=38,
        details={"ip": "10.0.0.5"},
    ),
]

# -- Workspaces ------------------------------------------------------------
ws1 = workspace_manager.create_workspace("Engineering", "Core engineering team", "u-001")
ws2 = workspace_manager.create_workspace("Research", "AI research group", "u-002")

# -- Cost: seed some usage data --------------------------------------------
cost_manager.record_usage("llama-3.1-70b", 15000, 3000, 0.0, task_id="code-review")
cost_manager.record_usage("mistral-7b", 8000, 2000, 0.0, task_id="summarize")
cost_manager.record_usage("llama-3.1-70b", 20000, 5000, 0.0, task_id="code-review")


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class BridgeHandler(BaseHTTPRequestHandler):
    """Handles GET requests from the Express API."""

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    # Suppress default logging to stderr for cleaner output
    def log_message(self, format, *args):
        sys.stderr.write(f"[bridge] {format % args}\n")

    def do_GET(self):
        path = self.path.split("?")[0]  # strip query string

        if path == "/bridge/hardware":
            self._handle_hardware()
        elif path == "/bridge/users":
            self._handle_users()
        elif path == "/bridge/audit":
            self._handle_audit()
        elif path == "/bridge/audit/stats":
            self._handle_audit_stats()
        elif path == "/bridge/fleet/status":
            self._handle_fleet_status()
        elif path.startswith("/bridge/compliance/"):
            framework = path.split("/bridge/compliance/")[1]
            self._handle_compliance(framework)
        elif path == "/bridge/cost":
            self._handle_cost()
        elif path == "/bridge/workspaces":
            self._handle_workspaces()
        else:
            self._send_error(404, f"Unknown bridge endpoint: {path}")

    # -- Endpoint handlers --------------------------------------------------

    def _handle_hardware(self):
        profile = hardware_detector.detect()
        recommendation = HardwareDetector.recommend_model(profile)
        ollama_config = HardwareDetector.get_ollama_config(profile)
        self._send_json({
            "profile": profile.to_dict(),
            "recommendation": asdict(recommendation),
            "ollama_config": ollama_config,
        })

    def _handle_users(self):
        # Return API key users with their metadata
        users = []
        for key, info in auth_manager._api_keys.items():
            users.append({
                "user_id": info["user_id"],
                "username": info["username"],
                "provider": "api_key",
                "api_key_prefix": key[:8] + "...",
            })
        self._send_json(users)

    def _handle_audit(self):
        events = [e.to_dict() for e in _demo_audit_events]
        self._send_json({
            "total": len(events),
            "offset": 0,
            "limit": 50,
            "events": events,
        })

    def _handle_audit_stats(self):
        by_severity = {}
        by_agent = {}
        for event in _demo_audit_events:
            by_severity[event.severity] = by_severity.get(event.severity, 0) + 1
            by_agent[event.agent] = by_agent.get(event.agent, 0) + 1
        self._send_json({
            "total_events": len(_demo_audit_events),
            "by_severity": by_severity,
            "by_agent": by_agent,
        })

    def _handle_fleet_status(self):
        profile = hardware_detector.detect()
        recommendation = HardwareDetector.recommend_model(profile)
        self._send_json({
            "active_devices": 1,
            "total_devices": 1,
            "model_distribution": {recommendation.model_name: 1},
            "local_hardware": profile.to_dict(),
        })

    def _handle_compliance(self, framework_name):
        framework_map = {
            "SOC2": ComplianceFramework.SOC2,
            "soc2": ComplianceFramework.SOC2,
            "GDPR": ComplianceFramework.GDPR,
            "gdpr": ComplianceFramework.GDPR,
            "HIPAA": ComplianceFramework.HIPAA,
            "hipaa": ComplianceFramework.HIPAA,
        }
        framework = framework_map.get(framework_name)
        if framework is None:
            self._send_error(400, f"Unknown framework: {framework_name}. Use SOC2, GDPR, or HIPAA.")
            return

        audit_dicts = [e.to_dict() for e in _demo_audit_events]
        period_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2026, 12, 31, tzinfo=timezone.utc)

        report = compliance_reporter.generate_report(
            framework, audit_dicts, period_start, period_end
        )
        self._send_json(compliance_reporter.export_dict(report))

    def _handle_cost(self):
        report = cost_manager.get_report()
        self._send_json(report.to_dict())

    def _handle_workspaces(self):
        workspaces = workspace_manager.list_workspaces()
        self._send_json([ws.to_dict() for ws in workspaces])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    port = int(os.environ.get("BRIDGE_PORT", 7892))
    server = HTTPServer(("127.0.0.1", port), BridgeHandler)
    print(f"IntentOS Python bridge listening on http://127.0.0.1:{port}")
    print(f"Project root: {PROJECT_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
