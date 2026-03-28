"""
IntentOS Audit Log Viewer.

Provides AuditViewer class for reading, filtering, formatting, and writing
audit log entries in JSONL format.

Standard AuditEntry format:
    {
        "timestamp": "ISO8601",
        "task_id": "uuid",
        "agent": "file_agent",
        "action": "move_file",
        "paths_accessed": ["/path/to/file"],
        "result": "success",
        "duration_ms": 150,
        "initiated_by": "john",
        "details": {}
    }
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_LOG_PATH = Path.home() / ".intentos" / "logs" / "audit.jsonl"


class AuditViewer:
    """Reads, filters, formats, and writes audit log entries."""

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @staticmethod
    def read_logs(log_path: Path) -> List[Dict[str, Any]]:
        """Read a JSONL audit log and return a list of entry dicts.

        - Returns [] for missing or empty files.
        - Skips corrupted (non-JSON) lines silently.
        """
        log_path = Path(log_path)
        if not log_path.exists():
            return []

        entries: List[Dict[str, Any]] = []
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
        return entries

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    @staticmethod
    def filter_by_agent(entries: List[Dict], agent_name: str) -> List[Dict]:
        """Return entries matching the given agent name."""
        return [e for e in entries if e.get("agent") == agent_name]

    @staticmethod
    def filter_by_status(entries: List[Dict], status: str) -> List[Dict]:
        """Return entries matching the given result status."""
        return [e for e in entries if e.get("result") == status]

    @staticmethod
    def filter_by_date(
        entries: List[Dict],
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> List[Dict]:
        """Return entries within the given ISO-8601 date range.

        Both *after* and *before* are inclusive bounds.  Either may be None.
        """
        result = entries
        if after is not None:
            after_dt = datetime.fromisoformat(after)
            result = [
                e for e in result
                if datetime.fromisoformat(e["timestamp"]) >= after_dt
            ]
        if before is not None:
            before_dt = datetime.fromisoformat(before)
            result = [
                e for e in result
                if datetime.fromisoformat(e["timestamp"]) <= before_dt
            ]
        return result

    @staticmethod
    def filter_by_action(entries: List[Dict], action: str) -> List[Dict]:
        """Return entries matching the given action."""
        return [e for e in entries if e.get("action") == action]

    # ------------------------------------------------------------------
    # Display Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _relative_time(iso_ts: str) -> str:
        """Convert an ISO-8601 timestamp to a human-friendly relative string.

        Examples: "2 minutes ago", "Today at 2:32 PM", "Yesterday at 10:15 AM",
                  "Mar 15 at 3:00 PM".
        """
        try:
            ts = datetime.fromisoformat(iso_ts)
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - ts
            total_seconds = diff.total_seconds()

            if total_seconds < 60:
                return "just now"
            if total_seconds < 3600:
                mins = int(total_seconds // 60)
                return f"{mins} minute{'s' if mins != 1 else ''} ago"
            if total_seconds < 7200:
                return "1 hour ago"

            # Check if same calendar day
            now_local = now
            ts_local = ts
            if now_local.date() == ts_local.date():
                return "Today at " + ts_local.strftime("%-I:%M %p")
            if (now_local.date() - ts_local.date()).days == 1:
                return "Yesterday at " + ts_local.strftime("%-I:%M %p")

            return ts_local.strftime("%b %-d at %-I:%M %p")
        except Exception:
            return iso_ts

    @staticmethod
    def format_entry(entry: Dict) -> str:
        """Format one audit entry as a human-readable single line.

        Example: "Today at 2:32 PM -- file_agent.move_file -> success (150ms)"
        """
        ts = AuditViewer._relative_time(entry.get("timestamp", ""))
        agent = entry.get("agent", "unknown")
        action = entry.get("action", "unknown")
        result = entry.get("result", "?")
        duration = entry.get("duration_ms", 0)
        return f"{ts} \u2014 {agent}.{action} \u2192 {result} ({duration}ms)"

    @staticmethod
    def format_entries(entries: List[Dict], limit: int = 20) -> str:
        """Format multiple entries with a header. Respects *limit*."""
        limited = entries[-limit:] if len(entries) > limit else entries
        lines = ["=== Audit Log ==="]
        for entry in limited:
            lines.append("  " + AuditViewer.format_entry(entry))
        return "\n".join(lines)

    @staticmethod
    def format_summary(entries: List[Dict]) -> str:
        """Return a summary: total events, by agent, by status, time range."""
        total = len(entries)
        agent_counts: Counter = Counter(e.get("agent", "unknown") for e in entries)
        status_counts: Counter = Counter(e.get("result", "unknown") for e in entries)

        lines = ["=== Audit Summary ==="]
        lines.append(f"  Total events: {total}")

        lines.append("  By agent:")
        for agent, count in agent_counts.most_common():
            lines.append(f"    {agent}: {count}")

        lines.append("  By status:")
        for status, count in status_counts.most_common():
            lines.append(f"    {status}: {count}")

        if entries:
            timestamps = []
            for e in entries:
                try:
                    timestamps.append(datetime.fromisoformat(e["timestamp"]))
                except (KeyError, ValueError):
                    continue
            if timestamps:
                earliest = min(timestamps)
                latest = max(timestamps)
                lines.append(f"  Time range: {earliest.isoformat()} to {latest.isoformat()}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Recent Logs
    # ------------------------------------------------------------------

    @staticmethod
    def recent(log_path: Path, n: int = 10) -> List[Dict[str, Any]]:
        """Return the last *n* entries from the log file."""
        all_entries = AuditViewer.read_logs(log_path)
        return all_entries[-n:]

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @staticmethod
    def write_entry(log_path: Path, entry_dict: Dict[str, Any]) -> None:
        """Append one JSONL line. Creates file and parent dirs if needed."""
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry_dict, default=str) + "\n")

    # ------------------------------------------------------------------
    # Default path helper (patchable in tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _default_log_path() -> Path:
        """Return the default audit log path."""
        return _DEFAULT_LOG_PATH
