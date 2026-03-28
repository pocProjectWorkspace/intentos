"""Tests for the IntentOS SIEM Integration module (Phase 3B.3)."""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import urllib.request
import urllib.error

import pytest

from core.enterprise.siem import (
    AuditEvent,
    ExportFormat,
    ExportDestination,
    EventFilter,
    SIEMExporter,
    SEVERITY_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_event():
    return AuditEvent(
        timestamp=datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc),
        event_id="evt-001",
        event_type="file.read",
        severity="info",
        agent="research-agent",
        action="read_file",
        user="alice",
        paths_accessed=["/data/report.txt"],
        result="success",
        duration_ms=42,
        details={"bytes_read": 1024, "encoding": "utf-8"},
    )


@pytest.fixture
def warning_event():
    return AuditEvent(
        timestamp=datetime(2026, 3, 28, 13, 0, 0, tzinfo=timezone.utc),
        event_id="evt-002",
        event_type="auth.failure",
        severity="warning",
        agent="login-agent",
        action="authenticate",
        user="bob",
        paths_accessed=[],
        result="failure",
        duration_ms=150,
        details={"reason": "invalid_credentials"},
    )


@pytest.fixture
def critical_event():
    return AuditEvent(
        timestamp=datetime(2026, 3, 28, 14, 0, 0, tzinfo=timezone.utc),
        event_id="evt-003",
        event_type="file.delete",
        severity="critical",
        agent="cleanup-agent",
        action="delete_file",
        user="admin",
        paths_accessed=["/data/secrets.db"],
        result="success",
        duration_ms=5,
        details={},
    )


@pytest.fixture
def empty_details_event():
    return AuditEvent(
        timestamp=datetime(2026, 3, 28, 15, 0, 0, tzinfo=timezone.utc),
        event_id="evt-004",
        event_type="system.ping",
        severity="info",
        agent="monitor",
        action="ping",
        user="system",
        paths_accessed=[],
        result="success",
        duration_ms=1,
        details={},
    )


@pytest.fixture
def unicode_event():
    return AuditEvent(
        timestamp=datetime(2026, 3, 28, 16, 0, 0, tzinfo=timezone.utc),
        event_id="evt-005",
        event_type="file.read",
        severity="info",
        agent="i18n-agent",
        action="read_file",
        user="tanaka-san",
        paths_accessed=["/data/reports/2026-Q1.txt"],
        result="success",
        duration_ms=30,
        details={"note": "Rapport trimestriel -- donnees en francais et japonais"},
    )


@pytest.fixture
def long_paths_event():
    paths = [f"/data/files/dir_{i}/file_{i}.txt" for i in range(200)]
    return AuditEvent(
        timestamp=datetime(2026, 3, 28, 17, 0, 0, tzinfo=timezone.utc),
        event_id="evt-006",
        event_type="file.scan",
        severity="info",
        agent="scanner-agent",
        action="bulk_scan",
        user="system",
        paths_accessed=paths,
        result="success",
        duration_ms=5000,
        details={"total_files": 200},
    )


@pytest.fixture
def exporter():
    return SIEMExporter()


# ===========================================================================
# 1-2: AuditEvent model
# ===========================================================================

class TestAuditEvent:
    """Tests 1-2: AuditEvent model and serialization."""

    def test_audit_event_has_all_fields(self, sample_event):
        """Test 1: AuditEvent contains all required fields."""
        assert isinstance(sample_event.timestamp, datetime)
        assert isinstance(sample_event.event_id, str)
        assert isinstance(sample_event.event_type, str)
        assert isinstance(sample_event.severity, str)
        assert isinstance(sample_event.agent, str)
        assert isinstance(sample_event.action, str)
        assert isinstance(sample_event.user, str)
        assert isinstance(sample_event.paths_accessed, list)
        assert isinstance(sample_event.result, str)
        assert isinstance(sample_event.duration_ms, int)
        assert isinstance(sample_event.details, dict)

    def test_audit_event_to_dict(self, sample_event):
        """Test 2: AuditEvent serializes to dict with all fields."""
        d = sample_event.to_dict()
        assert isinstance(d, dict)
        assert d["event_id"] == "evt-001"
        assert d["event_type"] == "file.read"
        assert d["severity"] == "info"
        assert d["agent"] == "research-agent"
        assert d["action"] == "read_file"
        assert d["user"] == "alice"
        assert d["paths_accessed"] == ["/data/report.txt"]
        assert d["result"] == "success"
        assert d["duration_ms"] == 42
        assert d["details"] == {"bytes_read": 1024, "encoding": "utf-8"}
        # timestamp should be ISO-format string
        assert "2026-03-28" in d["timestamp"]

    def test_audit_event_from_dict(self, sample_event):
        """AuditEvent round-trips through from_dict."""
        d = sample_event.to_dict()
        restored = AuditEvent.from_dict(d)
        assert restored.event_id == sample_event.event_id
        assert restored.severity == sample_event.severity
        assert restored.agent == sample_event.agent


# ===========================================================================
# 3-6: Syslog format (RFC 5424)
# ===========================================================================

class TestSyslogFormat:
    """Tests 3-6: RFC 5424 syslog formatting."""

    def test_format_syslog_returns_string(self, sample_event, exporter):
        """Test 3: format_syslog returns a non-empty string."""
        result = exporter.format_syslog(sample_event)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_syslog_contains_rfc5424_parts(self, sample_event, exporter):
        """Test 4: Syslog includes priority, version, timestamp, hostname, app-name, etc."""
        result = exporter.format_syslog(sample_event)
        # RFC 5424: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG
        assert result.startswith("<")
        assert ">1 " in result  # version 1
        assert "intentos" in result  # app-name
        assert "2026-03-28" in result

    def test_syslog_severity_mapping(self, sample_event, warning_event, critical_event, exporter):
        """Test 5: Severity maps correctly: info->6, warning->4, error->3, critical->2."""
        assert SEVERITY_MAP["info"] == 6
        assert SEVERITY_MAP["warning"] == 4
        assert SEVERITY_MAP["error"] == 3
        assert SEVERITY_MAP["critical"] == 2

        info_syslog = exporter.format_syslog(sample_event)
        # facility 1 (user) * 8 + severity -> <14> for info
        assert info_syslog.startswith("<14>")

        warning_syslog = exporter.format_syslog(warning_event)
        assert warning_syslog.startswith("<12>")  # 1*8+4

        critical_syslog = exporter.format_syslog(critical_event)
        assert critical_syslog.startswith("<10>")  # 1*8+2

    def test_syslog_structured_data(self, sample_event, exporter):
        """Test 6: Structured data includes event details as key-value pairs."""
        result = exporter.format_syslog(sample_event)
        # SD should be bracketed, e.g. [intentos@0 key="value" ...]
        assert "[intentos@0 " in result or "[intentos@0]" in result
        assert 'event_id="evt-001"' in result


# ===========================================================================
# 7-10: JSON format
# ===========================================================================

class TestJSONFormat:
    """Tests 7-10: JSON formatting."""

    def test_format_json_returns_string(self, sample_event, exporter):
        """Test 7: format_json returns a JSON string with all fields."""
        result = exporter.format_json(sample_event)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["event_id"] == "evt-001"
        assert parsed["agent"] == "research-agent"

    def test_json_is_parseable(self, sample_event, exporter):
        """Test 8: JSON output is valid and parseable."""
        result = exporter.format_json(sample_event)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_json_timestamp_iso8601(self, sample_event, exporter):
        """Test 9: Timestamps in ISO8601 format."""
        result = exporter.format_json(sample_event)
        parsed = json.loads(result)
        ts = parsed["timestamp"]
        # Should parse back as a datetime
        dt = datetime.fromisoformat(ts)
        assert dt.year == 2026

    def test_json_intentos_specific_fields(self, sample_event, exporter):
        """Test 10: JSON includes intentos-specific fields."""
        result = exporter.format_json(sample_event)
        parsed = json.loads(result)
        assert "agent" in parsed
        assert "action" in parsed
        assert "paths_accessed" in parsed
        assert parsed["paths_accessed"] == ["/data/report.txt"]


# ===========================================================================
# 11-13: CEF format
# ===========================================================================

class TestCEFFormat:
    """Tests 11-13: Common Event Format."""

    def test_format_cef_returns_string(self, sample_event, exporter):
        """Test 11: format_cef returns a CEF formatted string."""
        result = exporter.format_cef(sample_event)
        assert isinstance(result, str)
        assert result.startswith("CEF:0")

    def test_cef_header_structure(self, sample_event, exporter):
        """Test 12: CEF header: CEF:0|IntentOS|IntentKernel|1.0|event_type|event_name|severity|ext."""
        result = exporter.format_cef(sample_event)
        parts = result.split("|", 7)
        assert len(parts) == 8
        assert parts[0] == "CEF:0"
        assert parts[1] == "IntentOS"
        assert parts[2] == "IntentKernel"
        assert parts[3] == "1.0"
        assert parts[4] == "file.read"  # event_type
        assert parts[5] == "read_file"  # action as event_name

    def test_cef_extension_fields(self, sample_event, exporter):
        """Test 13: Extension includes src, dst, act, outcome, deviceCustomString."""
        result = exporter.format_cef(sample_event)
        ext = result.split("|", 7)[7]
        assert "act=" in ext
        assert "outcome=" in ext
        assert "src=" in ext or "suser=" in ext
        assert "deviceCustomString1=" in ext or "cs1=" in ext


# ===========================================================================
# 14-16: Batch export
# ===========================================================================

class TestBatchExport:
    """Tests 14-16: Batch file export."""

    def test_export_batch_writes_file(self, sample_event, warning_event, exporter):
        """Test 14: export_batch writes events to a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name
        try:
            exporter.export_batch([sample_event, warning_event], ExportFormat.JSON, path)
            with open(path) as f:
                content = f.read()
            assert "evt-001" in content
            assert "evt-002" in content
        finally:
            os.unlink(path)

    def test_export_batch_supports_all_formats(self, sample_event, exporter):
        """Test 15: Batch export supports SYSLOG, JSON, and CEF."""
        for fmt in ExportFormat:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
                path = f.name
            try:
                exporter.export_batch([sample_event], fmt, path)
                with open(path) as f:
                    content = f.read()
                assert len(content) > 0, f"Empty output for format {fmt}"
            finally:
                os.unlink(path)

    def test_export_batch_appends(self, sample_event, warning_event, exporter):
        """Test 16: Batch export appends to existing file, does not overwrite."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name
        try:
            exporter.export_batch([sample_event], ExportFormat.JSON, path)
            exporter.export_batch([warning_event], ExportFormat.JSON, path)
            with open(path) as f:
                content = f.read()
            assert "evt-001" in content
            assert "evt-002" in content
        finally:
            os.unlink(path)


# ===========================================================================
# 17-19: Webhook export
# ===========================================================================

class TestWebhookExport:
    """Tests 17-19: Webhook HTTP POST export."""

    @patch("core.enterprise.siem.urllib.request.urlopen")
    def test_export_webhook_sends_post(self, mock_urlopen, sample_event, exporter):
        """Test 17: export_webhook sends event via HTTP POST."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"ok"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        exporter.export_webhook(sample_event, "https://siem.example.com/ingest")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert isinstance(req, urllib.request.Request)
        assert req.full_url == "https://siem.example.com/ingest"
        assert req.method == "POST"

    @patch("core.enterprise.siem.urllib.request.urlopen")
    def test_export_webhook_retries_on_failure(self, mock_urlopen, sample_event, exporter):
        """Test 18: Retries on failure, max 3 retries."""
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        with pytest.raises(Exception):
            exporter.export_webhook(sample_event, "https://siem.example.com/ingest")

        assert mock_urlopen.call_count == 3

    @patch("core.enterprise.siem.urllib.request.urlopen")
    def test_export_webhook_timeout_configurable(self, mock_urlopen, sample_event, exporter):
        """Test 19: Timeout is configurable, default 10 seconds."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"ok"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        exporter.export_webhook(sample_event, "https://siem.example.com/ingest")
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 10

        mock_urlopen.reset_mock()
        mock_urlopen.return_value = mock_response
        exporter.export_webhook(sample_event, "https://siem.example.com/ingest", timeout=30)
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 30


# ===========================================================================
# 20-23: Stream configuration (destinations)
# ===========================================================================

class TestStreamConfiguration:
    """Tests 20-23: Destination management."""

    def test_add_destination(self, exporter):
        """Test 20: add_destination registers an export destination."""
        exporter.add_destination("local-syslog", ExportFormat.SYSLOG, "/var/log/intentos.log")
        destinations = exporter.list_destinations()
        assert len(destinations) == 1
        assert destinations[0].name == "local-syslog"

    def test_remove_destination(self, exporter):
        """Test 21: remove_destination unregisters a destination."""
        exporter.add_destination("webhook1", ExportFormat.JSON, "https://siem.example.com/ingest")
        exporter.remove_destination("webhook1")
        assert len(exporter.list_destinations()) == 0

    def test_list_destinations(self, exporter):
        """Test 22: list_destinations returns all registered destinations."""
        exporter.add_destination("file1", ExportFormat.SYSLOG, "/var/log/a.log")
        exporter.add_destination("webhook1", ExportFormat.JSON, "https://example.com/hook")
        destinations = exporter.list_destinations()
        assert len(destinations) == 2
        names = {d.name for d in destinations}
        assert names == {"file1", "webhook1"}

    def test_destination_target_types(self, exporter):
        """Test 23: Destination target can be file path or webhook URL."""
        exporter.add_destination("file", ExportFormat.CEF, "/var/log/cef.log")
        exporter.add_destination("hook", ExportFormat.JSON, "https://siem.corp.com/api")
        dests = {d.name: d for d in exporter.list_destinations()}
        assert dests["file"].target == "/var/log/cef.log"
        assert dests["hook"].target == "https://siem.corp.com/api"


# ===========================================================================
# 24-26: Filtering
# ===========================================================================

class TestFiltering:
    """Tests 24-26: Event filtering."""

    def test_add_filter_severity(self, exporter, sample_event, warning_event, critical_event):
        """Test 24-25: Filter by minimum severity."""
        filt = EventFilter(severity_min="warning")
        assert filt.matches(warning_event) is True
        assert filt.matches(critical_event) is True
        assert filt.matches(sample_event) is False  # info < warning

    def test_filter_by_event_type(self, sample_event, warning_event):
        """Test 26: Filter by event type."""
        filt = EventFilter(event_types=["file.read", "file.delete"])
        assert filt.matches(sample_event) is True  # file.read
        assert filt.matches(warning_event) is False  # auth.failure

    def test_filter_by_agent(self, sample_event, warning_event):
        """Filter by agent name."""
        filt = EventFilter(agents=["research-agent"])
        assert filt.matches(sample_event) is True
        assert filt.matches(warning_event) is False

    def test_filter_combined(self, sample_event, warning_event, critical_event):
        """Combined filter: severity + event_type."""
        filt = EventFilter(severity_min="warning", event_types=["auth.failure"])
        assert filt.matches(warning_event) is True
        assert filt.matches(sample_event) is False
        assert filt.matches(critical_event) is False  # file.delete not in types


# ===========================================================================
# 27-29: Edge cases
# ===========================================================================

class TestEdgeCases:
    """Tests 27-29: Edge cases."""

    def test_empty_details_valid_output(self, empty_details_event, exporter):
        """Test 27: Empty event details still produces valid output in all formats."""
        syslog = exporter.format_syslog(empty_details_event)
        assert isinstance(syslog, str) and len(syslog) > 0

        j = exporter.format_json(empty_details_event)
        parsed = json.loads(j)
        assert parsed["details"] == {}

        cef = exporter.format_cef(empty_details_event)
        assert cef.startswith("CEF:0")

    def test_unicode_in_event_fields(self, unicode_event, exporter):
        """Test 28: Unicode in event fields is properly encoded."""
        j = exporter.format_json(unicode_event)
        parsed = json.loads(j)
        assert "francais" in parsed["details"]["note"]

        syslog = exporter.format_syslog(unicode_event)
        assert isinstance(syslog, str)

        cef = exporter.format_cef(unicode_event)
        assert isinstance(cef, str)

    def test_long_paths_truncated_in_syslog_full_in_json(self, long_paths_event, exporter):
        """Test 29: Very long paths list truncated in syslog but full in JSON."""
        syslog = exporter.format_syslog(long_paths_event)
        # Syslog should truncate long paths
        assert len(syslog) < 10000

        j = exporter.format_json(long_paths_event)
        parsed = json.loads(j)
        assert len(parsed["paths_accessed"]) == 200
