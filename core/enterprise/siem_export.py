"""SIEM Export — format audit/inference logs for Splunk and Azure Sentinel."""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional


class SIEMExporter:
    """Exports IntentOS audit and inference data in SIEM-compatible formats."""

    def __init__(self, base_path: Optional[Path] = None):
        self._base = base_path or Path.home() / ".intentos"
        self._export_dir = self._base / "exports"
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def export_splunk_hec(self, events: List[Dict]) -> List[Dict]:
        """Format events for Splunk HTTP Event Collector (HEC).

        Output format matches Splunk CIM (Common Information Model).
        Each event wrapped in HEC envelope with index, sourcetype, source.
        """
        hec_events = []
        for event in events:
            hec_events.append({
                "time": event.get("timestamp", time.time()),
                "host": event.get("hostname", "unknown"),
                "source": "intentos:desktop",
                "sourcetype": self._get_sourcetype(event),
                "index": "intentos",
                "event": self._to_splunk_cim(event),
            })
        return hec_events

    def export_sentinel(self, events: List[Dict]) -> List[Dict]:
        """Format events for Azure Sentinel / Log Analytics.

        Uses the custom log format (DCR-based).
        """
        sentinel_events = []
        for event in events:
            sentinel_events.append({
                "TimeGenerated": event.get("timestamp", ""),
                "Computer": event.get("hostname", "unknown"),
                "Category": self._get_category(event),
                "OperationName": event.get("action", event.get("task_type", "")),
                "Result": event.get("status", event.get("result_status", "")),
                "DeviceId": event.get("device_id", ""),
                "AgentName": event.get("agent", ""),
                "CostUSD": event.get("cost_usd", 0),
                "InputTokens": event.get("input_tokens", 0),
                "OutputTokens": event.get("output_tokens", 0),
                "Model": event.get("model", ""),
                "Provider": event.get("provider", ""),
                "PrivacyMode": event.get("privacy_mode", ""),
                "Severity": event.get("severity", "info"),
                "Details": json.dumps(event.get("details", {})),
            })
        return sentinel_events

    def export_to_file(self, format: str = "splunk") -> str:
        """Read local audit + inference logs and export to a JSONL file.

        Returns the path to the exported file.
        """
        events = self._collect_local_events()

        if format == "splunk":
            formatted = self.export_splunk_hec(events)
        elif format == "sentinel":
            formatted = self.export_sentinel(events)
        else:
            formatted = events

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"intentos_export_{format}_{timestamp}.jsonl"
        filepath = self._export_dir / filename

        with open(filepath, "w") as f:
            for event in formatted:
                f.write(json.dumps(event) + "\n")

        return str(filepath)

    def _collect_local_events(self) -> List[Dict]:
        """Read audit.jsonl and inference.jsonl from local logs."""
        events = []
        for log_file in ["audit.jsonl", "inference.jsonl"]:
            path = self._base / "logs" / log_file
            if path.exists():
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
        return sorted(events, key=lambda e: e.get("timestamp", ""))

    def _get_sourcetype(self, event: Dict) -> str:
        if "input_tokens" in event:
            return "intentos:inference"
        if "tool" in event:
            return "intentos:agent_action"
        if "event_type" in event:
            return "intentos:compliance"
        return "intentos:audit"

    def _get_category(self, event: Dict) -> str:
        if "input_tokens" in event:
            return "AIInference"
        if "tool" in event:
            return "AgentExecution"
        if "event_type" in event:
            return "PolicyCompliance"
        return "AuditEvent"

    def _to_splunk_cim(self, event: Dict) -> Dict:
        """Map an IntentOS event to Splunk Common Information Model fields."""
        cim = {}
        for key, value in event.items():
            cim[key] = value
        # Ensure CIM standard fields
        cim.setdefault("action", event.get("task_type", "unknown"))
        cim.setdefault("user", event.get("initiated_by", ""))
        cim.setdefault("src", event.get("hostname", ""))
        return cim


def get_splunk_hec_sample() -> str:
    """Return a sample Splunk HEC event for documentation/testing."""
    return json.dumps({
        "time": 1712793600,
        "host": "alice-macbook",
        "source": "intentos:desktop",
        "sourcetype": "intentos:inference",
        "index": "intentos",
        "event": {
            "action": "llm_inference",
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 1200,
            "output_tokens": 350,
            "cost_usd": 0.0089,
            "latency_ms": 1340,
            "privacy_mode": "smart_routing",
            "device_id": "abc-123",
            "user": "alice",
        },
    }, indent=2)
