"""IntentOS SIEM Integration module (Phase 3B.3).

Exports audit events in standard security formats (Syslog RFC 5424, JSON, CEF)
for enterprise SIEM monitoring systems.
"""

from __future__ import annotations

import json
import socket
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_MAP: Dict[str, int] = {
    "info": 6,
    "warning": 4,
    "error": 3,
    "critical": 2,
}

_SEVERITY_ORDER = ["info", "warning", "error", "critical"]

# Syslog facility: user-level (1)
_SYSLOG_FACILITY = 1

# Max paths to include in syslog structured data before truncating
_SYSLOG_MAX_PATHS = 10


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AuditEvent:
    """A single auditable event from the IntentOS kernel."""

    timestamp: datetime
    event_id: str
    event_type: str
    severity: str
    agent: str
    action: str
    user: str
    paths_accessed: List[str]
    result: str
    duration_ms: int
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        data = dict(data)
        ts = data["timestamp"]
        if isinstance(ts, str):
            data["timestamp"] = datetime.fromisoformat(ts)
        return cls(**data)


class ExportFormat(Enum):
    SYSLOG = "syslog"
    JSON = "json"
    CEF = "cef"


@dataclass
class EventFilter:
    """Filter criteria for events."""

    severity_min: Optional[str] = None
    event_types: Optional[List[str]] = None
    agents: Optional[List[str]] = None

    def matches(self, event: AuditEvent) -> bool:
        if self.severity_min is not None:
            min_idx = _SEVERITY_ORDER.index(self.severity_min)
            evt_idx = _SEVERITY_ORDER.index(event.severity)
            if evt_idx < min_idx:
                return False
        if self.event_types is not None:
            if event.event_type not in self.event_types:
                return False
        if self.agents is not None:
            if event.agent not in self.agents:
                return False
        return True


@dataclass
class ExportDestination:
    """A registered export destination."""

    name: str
    format: ExportFormat
    target: str  # file path or URL
    filters: Optional[EventFilter] = None


# ---------------------------------------------------------------------------
# SIEMExporter
# ---------------------------------------------------------------------------

class SIEMExporter:
    """Formats and exports audit events to SIEM systems."""

    def __init__(self) -> None:
        self._destinations: Dict[str, ExportDestination] = {}

    # -- Formatting ---------------------------------------------------------

    @staticmethod
    def format_syslog(event: AuditEvent) -> str:
        """Format an event as RFC 5424 syslog string."""
        severity_num = SEVERITY_MAP.get(event.severity, 6)
        priority = _SYSLOG_FACILITY * 8 + severity_num
        version = 1
        timestamp = event.timestamp.isoformat()
        hostname = socket.gethostname()
        app_name = "intentos"
        procid = str(os.getpid())
        msgid = event.event_id

        # Build structured data
        sd_params: List[str] = []
        sd_params.append(f'event_id="{event.event_id}"')
        sd_params.append(f'event_type="{event.event_type}"')
        sd_params.append(f'agent="{event.agent}"')
        sd_params.append(f'action="{event.action}"')
        sd_params.append(f'user="{event.user}"')
        sd_params.append(f'result="{event.result}"')
        sd_params.append(f'duration_ms="{event.duration_ms}"')

        # Paths -- truncate for syslog
        paths = event.paths_accessed[:_SYSLOG_MAX_PATHS]
        if paths:
            paths_str = ",".join(paths)
            sd_params.append(f'paths="{paths_str}"')
        if len(event.paths_accessed) > _SYSLOG_MAX_PATHS:
            sd_params.append(
                f'paths_truncated="true" paths_total="{len(event.paths_accessed)}"'
            )

        # Include details as SD params
        for k, v in event.details.items():
            safe_val = str(v).replace('"', '\\"').replace("\\", "\\\\").replace("]", "\\]")
            sd_params.append(f'{k}="{safe_val}"')

        sd = "[intentos@0 " + " ".join(sd_params) + "]"

        msg = f"{event.event_type}: {event.action} by {event.user} -> {event.result}"

        return f"<{priority}>{version} {timestamp} {hostname} {app_name} {procid} {msgid} {sd} {msg}"

    @staticmethod
    def format_json(event: AuditEvent) -> str:
        """Format an event as a JSON string."""
        return json.dumps(event.to_dict(), ensure_ascii=False)

    @staticmethod
    def format_cef(event: AuditEvent) -> str:
        """Format an event as a CEF (Common Event Format) string."""
        severity_num = SEVERITY_MAP.get(event.severity, 6)
        # CEF severity: map syslog numeric to CEF 0-10 scale
        cef_severity = severity_num

        # Header: CEF:0|Vendor|Product|Version|SignatureID|Name|Severity|Extension
        header = (
            f"CEF:0|IntentOS|IntentKernel|1.0"
            f"|{event.event_type}"
            f"|{event.action}"
            f"|{cef_severity}"
        )

        # Extension key=value pairs
        ext_parts: List[str] = []
        ext_parts.append(f"suser={event.user}")
        ext_parts.append(f"act={event.action}")
        ext_parts.append(f"outcome={event.result}")
        ext_parts.append(f"src={event.agent}")
        ext_parts.append(f"deviceCustomString1={event.event_id}")
        ext_parts.append(f"cs1Label=eventId")
        if event.paths_accessed:
            ext_parts.append(
                f"deviceCustomString2={','.join(event.paths_accessed)}"
            )
            ext_parts.append(f"cs2Label=pathsAccessed")
        ext_parts.append(f"deviceCustomNumber1={event.duration_ms}")
        ext_parts.append(f"cn1Label=durationMs")

        for k, v in event.details.items():
            safe_v = str(v).replace("=", "\\=").replace("|", "\\|")
            ext_parts.append(f"cs3Label={k} deviceCustomString3={safe_v}")

        extension = " ".join(ext_parts)
        return f"{header}|{extension}"

    # -- Formatting dispatch ------------------------------------------------

    def _format_event(self, event: AuditEvent, fmt: ExportFormat) -> str:
        if fmt == ExportFormat.SYSLOG:
            return self.format_syslog(event)
        elif fmt == ExportFormat.JSON:
            return self.format_json(event)
        elif fmt == ExportFormat.CEF:
            return self.format_cef(event)
        raise ValueError(f"Unknown format: {fmt}")

    # -- Batch export -------------------------------------------------------

    def export_batch(
        self,
        events: List[AuditEvent],
        fmt: ExportFormat,
        output_path: str,
    ) -> None:
        """Write events to a file in the given format. Appends to existing files."""
        with open(output_path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(self._format_event(event, fmt))
                f.write("\n")

    # -- Webhook export -----------------------------------------------------

    def export_webhook(
        self,
        event: AuditEvent,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
        max_retries: int = 3,
    ) -> None:
        """Send an event via HTTP POST to a webhook URL with retries."""
        body = self.format_json(event).encode("utf-8")
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(
            url,
            data=body,
            headers=req_headers,
            method="POST",
        )

        last_exc: Optional[Exception] = None
        for _ in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp.read()
                return
            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
                last_exc = exc

        raise last_exc  # type: ignore[misc]

    # -- Destination management ---------------------------------------------

    def add_destination(
        self,
        name: str,
        fmt: ExportFormat,
        target: str,
        filters: Optional[EventFilter] = None,
    ) -> None:
        self._destinations[name] = ExportDestination(
            name=name, format=fmt, target=target, filters=filters
        )

    def remove_destination(self, name: str) -> None:
        self._destinations.pop(name, None)

    def list_destinations(self) -> List[ExportDestination]:
        return list(self._destinations.values())

    # -- Export to all destinations -----------------------------------------

    def export_event(self, event: AuditEvent) -> None:
        """Send an event to all registered destinations that match filters."""
        for dest in self._destinations.values():
            if dest.filters and not dest.filters.matches(event):
                continue
            if dest.target.startswith("http://") or dest.target.startswith("https://"):
                self.export_webhook(event, dest.target)
            else:
                self.export_batch([event], dest.format, dest.target)
