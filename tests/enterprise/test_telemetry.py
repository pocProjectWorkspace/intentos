"""Tests for core.enterprise.telemetry — TelemetryReporter."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _project_root)

from core.enterprise.telemetry import TelemetryReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_policy_mock(managed=True):
    mock = MagicMock()
    mock.is_managed = managed
    mock.get_compliance_status.return_value = {
        "policy_version": "1.0",
        "privacy_mode": "local_only",
        "org_id": "org-123",
        "device_id": "dev-abc",
    }
    return mock


def _make_llm_mock():
    mock = MagicMock()
    mock.get_inference_stats.return_value = {
        "calls_local": 5,
        "calls_cloud": 3,
        "total_calls": 8,
        "total_latency_ms": 1000,
    }
    mock_usage = MagicMock()
    mock_usage.call_count = 3
    mock_usage.cost_usd = 0.5
    mock_report = MagicMock()
    mock_report.total_spent_usd = 0.5
    mock_report.by_model = {"claude-sonnet-4": mock_usage}
    mock.get_cost_report.return_value = mock_report
    return mock


def _make_security_mock():
    mock = MagicMock()
    mock.get_stats.return_value = {
        "total_scans": 10,
        "inputs_blocked": 1,
        "outputs_blocked": 0,
        "leaks_redacted": 2,
        "policy_violations": 0,
    }
    return mock


def _make_reporter(tmp_path=None, policy=None, llm=None, security=None):
    return TelemetryReporter(
        console_url="https://console.test.com",
        device_token="tok-secret",
        interval=60,
        policy_engine=policy,
        llm_service=llm,
        security_pipeline=security,
        base_path=Path(tmp_path) if tmp_path else None,
    )


def _urlopen_response(body: dict):
    """Return a mock suitable for urllib.request.urlopen."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode("utf-8")
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPayload:
    def test_payload_schema(self):
        r = _make_reporter(policy=_make_policy_mock(), llm=_make_llm_mock(),
                           security=_make_security_mock())
        payload = r._collect_payload()

        assert payload["schema_version"] == "1.0"
        assert payload["type"] == "heartbeat"
        for key in ("device_id", "org_id", "timestamp", "system",
                    "compliance", "usage", "security"):
            assert key in payload, f"Missing top-level key: {key}"
        assert isinstance(payload["system"], dict)
        for sk in ("hostname", "os", "intentos_version", "uptime_seconds"):
            assert sk in payload["system"]

    def test_payload_compliance_managed(self):
        r = _make_reporter(policy=_make_policy_mock(managed=True))
        payload = r._collect_payload()
        c = payload["compliance"]

        assert c["policy_loaded"] is True
        assert c["policy_version"] == "1.0"
        assert c["privacy_mode"] == "local_only"
        assert c["org_id"] == "org-123"

    def test_payload_compliance_unmanaged(self):
        r = _make_reporter(policy=None)
        payload = r._collect_payload()
        assert payload["compliance"]["policy_loaded"] is False

    def test_payload_usage_with_llm(self):
        r = _make_reporter(llm=_make_llm_mock())
        payload = r._collect_payload()
        inf = payload["usage"]["inference"]

        assert inf["calls_local"] == 5
        assert inf["calls_cloud"] == 3
        assert inf["total_cost_usd"] == 0.5
        assert "claude-sonnet-4" in inf["by_model"]
        assert inf["by_model"]["claude-sonnet-4"]["calls"] == 3
        assert inf["by_model"]["claude-sonnet-4"]["cost_usd"] == 0.5

    def test_payload_security_stats(self):
        r = _make_reporter(security=_make_security_mock())
        payload = r._collect_payload()
        sec = payload["security"]

        assert sec["total_scans"] == 10
        assert sec["inputs_blocked"] == 1
        assert sec["outputs_blocked"] == 0
        assert sec["leaks_redacted"] == 2
        assert sec["policy_violations"] == 0


class TestSend:
    @patch("core.enterprise.telemetry.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_response(
            {"status": "ok", "policy_update": None}
        )
        r = _make_reporter()
        assert r.send_now() is True
        assert r._send_count == 1
        assert r._error_count == 0

    @patch("core.enterprise.telemetry.urllib.request.urlopen")
    def test_send_network_failure(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        r = _make_reporter()
        assert r.send_now() is False
        assert r._error_count == 1

    @patch("core.enterprise.telemetry.urllib.request.urlopen")
    def test_send_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://console.test.com/api/v1/telemetry/heartbeat",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b""),
        )
        r = _make_reporter()
        assert r.send_now() is False
        assert r._error_count == 1

    @patch("core.enterprise.telemetry.urllib.request.urlopen")
    def test_policy_update_on_response(self, mock_urlopen, tmp_path):
        policy_mock = _make_policy_mock()
        mock_urlopen.return_value = _urlopen_response({
            "status": "ok",
            "policy_update": {
                "version": "1.1",
                "policy_json": {"version": "1.1", "rules": []},
                "signature": "abc",
            },
        })
        r = _make_reporter(tmp_path=tmp_path, policy=policy_mock)
        assert r.send_now() is True

        policy_path = tmp_path / "policy.json"
        assert policy_path.exists()
        written = json.loads(policy_path.read_text())
        assert written["version"] == "1.1"
        assert written["signature"] == "abc"
        policy_mock.reload.assert_called_once()


class TestStatus:
    def test_get_status(self):
        r = _make_reporter()
        status = r.get_status()
        assert status["running"] is False
        assert status["console_url"] == "https://console.test.com"
        assert status["interval_seconds"] == 60
        assert status["send_count"] == 0
        assert status["error_count"] == 0

    @patch("core.enterprise.telemetry.urllib.request.urlopen")
    def test_get_status_after_send(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_response(
            {"status": "ok", "policy_update": None}
        )
        r = _make_reporter()
        r.send_now()
        status = r.get_status()
        assert status["send_count"] == 1
        assert status["last_send_ok"] is True
        assert status["last_send_time"] is not None


class TestLifecycle:
    def test_start_stop(self):
        r = _make_reporter()
        assert r._running is False

        r.start()
        assert r._running is True
        assert r._timer is not None

        r.stop()
        assert r._running is False
        assert r._timer is None

    @patch("core.enterprise.telemetry.threading.Timer")
    def test_timer_scheduling(self, mock_timer_cls):
        mock_timer = MagicMock()
        mock_timer_cls.return_value = mock_timer

        r = _make_reporter()
        r.start()

        mock_timer_cls.assert_called_once_with(60, r._tick)
        mock_timer.start.assert_called_once()
        assert mock_timer.daemon is True

        r.stop()
        mock_timer.cancel.assert_called_once()
