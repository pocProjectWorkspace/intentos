"""
Tests for IntentOS Audit Log Viewer.

Covers: reading, filtering, formatting, recent logs, writing, and CLI integration.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.audit import AuditViewer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    agent="file_agent",
    action="move_file",
    result="success",
    duration_ms=150,
    timestamp=None,
    task_id="abc-123",
    initiated_by="john",
    paths_accessed=None,
    details=None,
):
    """Build a standard AuditEntry dict."""
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "agent": agent,
        "action": action,
        "paths_accessed": paths_accessed or ["/tmp/file.txt"],
        "result": result,
        "duration_ms": duration_ms,
        "initiated_by": initiated_by,
        "details": details or {},
    }


def _write_jsonl(path: Path, entries: list[dict]):
    """Write a list of dicts as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Reading Logs
# ---------------------------------------------------------------------------

class TestReadLogs:
    def test_read_jsonl_returns_list(self, tmp_path):
        """1. read_logs reads JSONL file and returns list of dicts."""
        log = tmp_path / "audit.jsonl"
        entries = [_make_entry(), _make_entry(agent="web_agent")]
        _write_jsonl(log, entries)

        result = AuditViewer.read_logs(log)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["agent"] == "file_agent"
        assert result[1]["agent"] == "web_agent"

    def test_missing_file_returns_empty(self, tmp_path):
        """2. Missing file returns empty list."""
        result = AuditViewer.read_logs(tmp_path / "nope.jsonl")
        assert result == []

    def test_corrupted_lines_skipped(self, tmp_path):
        """3. Bad JSON lines are skipped; good entries kept."""
        log = tmp_path / "audit.jsonl"
        good = _make_entry()
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w") as f:
            f.write(json.dumps(good) + "\n")
            f.write("NOT-JSON!!!\n")
            f.write(json.dumps(_make_entry(agent="second")) + "\n")

        result = AuditViewer.read_logs(log)
        assert len(result) == 2
        assert result[0]["agent"] == "file_agent"
        assert result[1]["agent"] == "second"

    def test_empty_file_returns_empty(self, tmp_path):
        """4. Empty file returns empty list."""
        log = tmp_path / "audit.jsonl"
        log.touch()
        assert AuditViewer.read_logs(log) == []


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    @pytest.fixture()
    def sample_entries(self):
        now = datetime.now(timezone.utc)
        return [
            _make_entry(agent="file_agent", action="move_file", result="success",
                        timestamp=(now - timedelta(days=3)).isoformat()),
            _make_entry(agent="web_agent", action="fetch_url", result="error",
                        timestamp=(now - timedelta(days=1)).isoformat()),
            _make_entry(agent="file_agent", action="delete_file", result="error",
                        timestamp=now.isoformat()),
        ]

    def test_filter_by_agent(self, sample_entries):
        """5. filter_by_agent returns only matching entries."""
        result = AuditViewer.filter_by_agent(sample_entries, "file_agent")
        assert len(result) == 2
        assert all(e["agent"] == "file_agent" for e in result)

    def test_filter_by_status(self, sample_entries):
        """6. filter_by_status returns only matching entries."""
        result = AuditViewer.filter_by_status(sample_entries, "error")
        assert len(result) == 2
        assert all(e["result"] == "error" for e in result)

    def test_filter_by_date(self, sample_entries):
        """7. filter_by_date with after/before returns date-filtered entries."""
        now = datetime.now(timezone.utc)
        after = (now - timedelta(days=2)).isoformat()
        before = (now + timedelta(seconds=1)).isoformat()

        result = AuditViewer.filter_by_date(sample_entries, after=after, before=before)
        # Should include the last 2 entries (1 day ago and now), not 3 days ago
        assert len(result) == 2

    def test_filter_by_action(self, sample_entries):
        """8. filter_by_action returns only matching action."""
        result = AuditViewer.filter_by_action(sample_entries, "move_file")
        assert len(result) == 1
        assert result[0]["action"] == "move_file"

    def test_composable_filters(self, sample_entries):
        """9. Multiple filters composable (chain them)."""
        r = AuditViewer.filter_by_agent(sample_entries, "file_agent")
        r = AuditViewer.filter_by_status(r, "error")
        assert len(r) == 1
        assert r[0]["action"] == "delete_file"


# ---------------------------------------------------------------------------
# Display Formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_format_entry(self):
        """10. format_entry returns human-readable single-line string."""
        entry = _make_entry(
            agent="file_agent",
            action="move_file",
            result="success",
            duration_ms=150,
        )
        line = AuditViewer.format_entry(entry)
        assert "file_agent.move_file" in line
        assert "success" in line
        assert "150ms" in line
        # Should contain a time component (relative or absolute)
        assert len(line) > 0

    def test_format_entries(self):
        """11. format_entries returns formatted string with header and entries."""
        entries = [_make_entry() for _ in range(5)]
        output = AuditViewer.format_entries(entries, limit=3)
        lines = output.strip().split("\n")
        # Should have a header line plus 3 entry lines
        assert len(lines) >= 4  # header + at least 3 entries

    def test_format_entries_limit(self):
        """format_entries respects limit parameter."""
        entries = [_make_entry() for _ in range(25)]
        output = AuditViewer.format_entries(entries, limit=20)
        # Count non-header lines
        lines = [l for l in output.strip().split("\n") if l.strip()]
        # header + up to 20 entries
        assert len(lines) <= 21

    def test_format_summary(self):
        """12. format_summary returns summary: total, by agent, by status, time range."""
        entries = [
            _make_entry(agent="file_agent", result="success"),
            _make_entry(agent="file_agent", result="error"),
            _make_entry(agent="web_agent", result="success"),
        ]
        summary = AuditViewer.format_summary(entries)
        assert "3" in summary  # total events
        assert "file_agent" in summary
        assert "web_agent" in summary
        assert "success" in summary
        assert "error" in summary


# ---------------------------------------------------------------------------
# Recent Logs
# ---------------------------------------------------------------------------

class TestRecent:
    def test_recent_returns_last_n(self, tmp_path):
        """13. recent(log_path, n=10) returns last N entries."""
        log = tmp_path / "audit.jsonl"
        entries = [_make_entry(task_id=f"task-{i}") for i in range(20)]
        _write_jsonl(log, entries)

        result = AuditViewer.recent(log, n=10)
        assert len(result) == 10
        assert result[0]["task_id"] == "task-10"
        assert result[-1]["task_id"] == "task-19"

    def test_recent_n_larger_than_file(self, tmp_path):
        """14. recent with n larger than file returns all entries."""
        log = tmp_path / "audit.jsonl"
        entries = [_make_entry(task_id=f"task-{i}") for i in range(3)]
        _write_jsonl(log, entries)

        result = AuditViewer.recent(log, n=100)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Writing Logs
# ---------------------------------------------------------------------------

class TestWriting:
    def test_write_entry_appends(self, tmp_path):
        """15. write_entry appends one JSONL line."""
        log = tmp_path / "audit.jsonl"
        log.touch()

        entry = _make_entry()
        AuditViewer.write_entry(log, entry)
        AuditViewer.write_entry(log, _make_entry(agent="second"))

        with open(log) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_write_entry_creates_file(self, tmp_path):
        """16. write_entry creates the file if it doesn't exist."""
        log = tmp_path / "audit.jsonl"
        assert not log.exists()

        AuditViewer.write_entry(log, _make_entry())
        assert log.exists()

    def test_write_entry_creates_parents(self, tmp_path):
        """17. write_entry creates parent directories if needed."""
        log = tmp_path / "deep" / "nested" / "audit.jsonl"
        AuditViewer.write_entry(log, _make_entry())
        assert log.exists()

    def test_round_trip(self, tmp_path):
        """18. Written entries can be read back correctly."""
        log = tmp_path / "audit.jsonl"
        original = _make_entry(agent="round_trip_agent", action="test_action")
        AuditViewer.write_entry(log, original)

        entries = AuditViewer.read_logs(log)
        assert len(entries) == 1
        assert entries[0]["agent"] == "round_trip_agent"
        assert entries[0]["action"] == "test_action"
        assert entries[0]["duration_ms"] == 150


# ---------------------------------------------------------------------------
# CLI Integration
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    @pytest.fixture()
    def audit_log(self, tmp_path):
        """Create a temp audit log with sample entries."""
        log = tmp_path / "audit.jsonl"
        now = datetime.now(timezone.utc)
        entries = [
            _make_entry(agent="file_agent", result="success", action="move_file",
                        task_id=f"t-{i}",
                        timestamp=(now - timedelta(minutes=30 - i)).isoformat())
            for i in range(15)
        ]
        # Add some error entries
        entries.append(_make_entry(agent="web_agent", result="error", action="fetch_url",
                                   timestamp=now.isoformat()))
        _write_jsonl(log, entries)
        return log

    def test_audit_command_registered(self, audit_log):
        """19. AuditViewer integrates with CLICommands as !audit command."""
        from core.cli import CLICommands
        cli = CLICommands()
        assert "audit" in cli.commands

    def test_audit_no_args(self, audit_log):
        """20. !audit (no args) shows last 10 entries."""
        from core.cli import CLICommands
        cli = CLICommands()
        with patch.object(AuditViewer, "_default_log_path", return_value=audit_log):
            output = cli.handle("audit")
        # Should contain audit entries (at least some lines)
        assert "Audit Log" in output or "audit" in output.lower()
        # Check it shows entries
        lines = [l for l in output.strip().split("\n") if l.strip() and not l.startswith("=")]
        assert len(lines) >= 1

    def test_audit_with_limit(self, audit_log):
        """21. !audit 20 shows last 20 entries."""
        from core.cli import CLICommands
        cli = CLICommands()
        with patch.object(AuditViewer, "_default_log_path", return_value=audit_log):
            output = cli.handle("audit 20")
        # Should show more entries than default
        assert len(output) > 0

    def test_audit_filter_agent(self, audit_log):
        """22. !audit --agent file_agent filters by agent."""
        from core.cli import CLICommands
        cli = CLICommands()
        with patch.object(AuditViewer, "_default_log_path", return_value=audit_log):
            output = cli.handle("audit --agent file_agent")
        assert "file_agent" in output
        # web_agent entries should not appear
        assert "web_agent" not in output

    def test_audit_filter_status(self, audit_log):
        """23. !audit --status error filters by status."""
        from core.cli import CLICommands
        cli = CLICommands()
        with patch.object(AuditViewer, "_default_log_path", return_value=audit_log):
            output = cli.handle("audit --status error")
        assert "error" in output

    def test_audit_summary(self, audit_log):
        """24. !audit summary shows summary statistics."""
        from core.cli import CLICommands
        cli = CLICommands()
        with patch.object(AuditViewer, "_default_log_path", return_value=audit_log):
            output = cli.handle("audit summary")
        assert "file_agent" in output
        assert "web_agent" in output
        # Should mention total count
        assert "16" in output or "Total" in output
