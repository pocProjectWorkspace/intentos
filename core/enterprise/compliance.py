"""IntentOS Compliance Reporting Module (Phase 3B.4).

Auto-generates SOC2, GDPR, and HIPAA compliance reports from audit data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ComplianceFramework(str, Enum):
    SOC2 = "SOC2"
    GDPR = "GDPR"
    HIPAA = "HIPAA"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    control_id: str
    description: str
    evidence_type: str  # "log", "config", "attestation"
    timestamp: datetime
    data: Dict[str, Any]
    status: str  # "pass", "fail", "partial"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "description": self.description,
            "evidence_type": self.evidence_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "status": self.status,
        }


@dataclass
class ControlResult:
    control_id: str
    control_name: str
    status: str  # "pass", "fail", "partial", "no_evidence"
    evidence_items: List[EvidenceItem]
    notes: str = ""


@dataclass
class ComplianceReport:
    framework: ComplianceFramework
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    controls: List[ControlResult]
    overall_status: str  # "compliant", "non_compliant", "partially_compliant", "insufficient_data"
    summary: str = ""


# ---------------------------------------------------------------------------
# Control definitions
# ---------------------------------------------------------------------------

SOC2_CONTROLS = {
    "CC6.1": {
        "name": "Access Control",
        "description": "Logical and physical access controls to protect information assets.",
        "event_types": ["access_grant", "access_revoke", "path_grant"],
    },
    "CC6.7": {
        "name": "Encryption at Rest",
        "description": "Encryption of data at rest using approved algorithms.",
        "event_types": ["encryption_verification"],
    },
    "CC7.2": {
        "name": "System Monitoring",
        "description": "Monitoring of system components for anomalies and completeness.",
        "event_types": ["audit_log_entry"],
    },
    "CC8.1": {
        "name": "Change Management",
        "description": "Authorized, tested, and approved changes to infrastructure and software.",
        "event_types": ["destructive_op_confirmed"],
    },
}

GDPR_CONTROLS = {
    "Art.5": {
        "name": "Data Minimization (Article 5)",
        "description": "Personal data shall be adequate, relevant, and limited to what is necessary.",
        "event_types": ["data_processing", "network_check"],
    },
    "Art.17": {
        "name": "Right to Erasure (Article 17)",
        "description": "The data subject shall have the right to obtain erasure of personal data.",
        "event_types": ["data_deletion"],
    },
    "Art.30": {
        "name": "Records of Processing (Article 30)",
        "description": "Each controller shall maintain a record of processing activities.",
        "event_types": ["audit_log_entry", "data_processing"],
    },
    "Art.32": {
        "name": "Security of Processing (Article 32)",
        "description": "Appropriate technical and organisational measures to ensure security.",
        "event_types": ["encryption_verification", "sandbox_enforcement"],
    },
}

HIPAA_CONTROLS = {
    "164.312(a)(1)": {
        "name": "Access Control",
        "description": "Implement technical policies and procedures for access to ePHI.",
        "event_types": ["sandbox_enforcement", "path_grant", "access_grant"],
    },
    "164.312(a)(2)(iv)": {
        "name": "Encryption and Decryption",
        "description": "Implement a mechanism to encrypt and decrypt ePHI.",
        "event_types": ["encryption_verification"],
    },
    "164.312(b)": {
        "name": "Audit Controls",
        "description": "Implement mechanisms to record and examine activity in systems containing ePHI.",
        "event_types": ["audit_log_entry"],
    },
    "164.312(e)(1)": {
        "name": "Transmission Security",
        "description": "Implement technical security measures to guard against unauthorized access to ePHI during transmission.",
        "event_types": ["network_check"],
    },
}

FRAMEWORK_CONTROLS = {
    ComplianceFramework.SOC2: SOC2_CONTROLS,
    ComplianceFramework.GDPR: GDPR_CONTROLS,
    ComplianceFramework.HIPAA: HIPAA_CONTROLS,
}


# ---------------------------------------------------------------------------
# ComplianceReporter
# ---------------------------------------------------------------------------

class ComplianceReporter:
    """Generates compliance reports from audit event data."""

    def collect_evidence(
        self,
        framework: ComplianceFramework,
        audit_events: List[Dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> List[EvidenceItem]:
        """Collect evidence items for the given framework from audit events."""
        if not isinstance(framework, ComplianceFramework):
            raise ValueError(f"Unknown framework: {framework}")

        controls = FRAMEWORK_CONTROLS[framework]
        filtered_events = self._filter_events_by_period(audit_events, period_start, period_end)

        evidence: List[EvidenceItem] = []
        for control_id, control_def in controls.items():
            control_evidence = self._collect_control_evidence(
                control_id, control_def, filtered_events
            )
            evidence.extend(control_evidence)

        return evidence

    def generate_report(
        self,
        framework,
        audit_events: List[Dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> ComplianceReport:
        """Generate a full compliance report."""
        if not isinstance(framework, ComplianceFramework):
            raise ValueError(f"Unknown framework: {framework}")

        controls_def = FRAMEWORK_CONTROLS[framework]
        filtered_events = self._filter_events_by_period(audit_events, period_start, period_end)

        # Edge case: no audit events at all
        if not audit_events:
            control_results = [
                ControlResult(
                    control_id=cid,
                    control_name=cdef["name"],
                    status="no_evidence",
                    evidence_items=[],
                    notes="No audit events provided.",
                )
                for cid, cdef in controls_def.items()
            ]
            return ComplianceReport(
                framework=framework,
                generated_at=datetime.now(),
                period_start=period_start,
                period_end=period_end,
                controls=control_results,
                overall_status="insufficient_data",
                summary="No audit events were available for analysis.",
            )

        # Build control results
        control_results: List[ControlResult] = []
        for control_id, control_def in controls_def.items():
            evidence_items = self._collect_control_evidence(control_id, control_def, filtered_events)
            status = self._evaluate_evidence(control_id, evidence_items, filtered_events)
            control_results.append(
                ControlResult(
                    control_id=control_id,
                    control_name=control_def["name"],
                    status=status,
                    evidence_items=evidence_items,
                    notes=self._generate_control_notes(control_id, status, evidence_items),
                )
            )

        overall_status = self._compute_overall_status(control_results)
        summary = self._generate_summary(framework, control_results, overall_status)

        return ComplianceReport(
            framework=framework,
            generated_at=datetime.now(),
            period_start=period_start,
            period_end=period_end,
            controls=control_results,
            overall_status=overall_status,
            summary=summary,
        )

    def export_text(self, report: ComplianceReport) -> str:
        """Export a compliance report as human-readable text."""
        lines: List[str] = []
        lines.append("=" * 72)
        lines.append(f"  {report.framework.value} Compliance Report")
        lines.append("=" * 72)
        lines.append(f"Generated: {report.generated_at.isoformat()}")
        lines.append(f"Period:    {report.period_start.date()} to {report.period_end.date()}")
        lines.append(f"Status:    {report.overall_status.upper()}")
        lines.append("")
        lines.append("Summary")
        lines.append("-" * 72)
        lines.append(report.summary)
        lines.append("")
        lines.append("Control Details")
        lines.append("-" * 72)

        for ctrl in report.controls:
            lines.append(f"\n  [{ctrl.status.upper()}] {ctrl.control_id} - {ctrl.control_name}")
            if ctrl.notes:
                lines.append(f"    Notes: {ctrl.notes}")
            if ctrl.evidence_items:
                lines.append(f"    Evidence ({len(ctrl.evidence_items)} items):")
                for ev in ctrl.evidence_items:
                    lines.append(f"      - [{ev.status}] {ev.description}")

        lines.append("")
        lines.append("=" * 72)
        return "\n".join(lines)

    def export_dict(self, report: ComplianceReport) -> Dict[str, Any]:
        """Export a compliance report as a JSON-serializable dict."""
        return {
            "framework": report.framework.value,
            "generated_at": report.generated_at.isoformat(),
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "overall_status": report.overall_status,
            "summary": report.summary,
            "controls": [
                {
                    "control_id": ctrl.control_id,
                    "control_name": ctrl.control_name,
                    "status": ctrl.status,
                    "notes": ctrl.notes,
                    "evidence_items": [ev.to_dict() for ev in ctrl.evidence_items],
                }
                for ctrl in report.controls
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_events_by_period(
        self,
        events: List[Dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> List[Dict[str, Any]]:
        """Return only events whose timestamp falls within the period."""
        filtered = []
        for event in events:
            ts_raw = event.get("timestamp")
            if ts_raw is None:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw)
            except (ValueError, TypeError):
                continue
            if period_start <= ts <= period_end:
                filtered.append(event)
        return filtered

    def _collect_control_evidence(
        self,
        control_id: str,
        control_def: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> List[EvidenceItem]:
        """Collect evidence items for a single control from filtered events."""
        relevant_types = set(control_def.get("event_types", []))
        items: List[EvidenceItem] = []

        for event in events:
            if event.get("type") in relevant_types:
                ts_raw = event.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except (ValueError, TypeError):
                    ts = datetime.now()

                ev_status = self._assess_event_status(control_id, event)
                items.append(
                    EvidenceItem(
                        control_id=control_id,
                        description=self._describe_event(event),
                        evidence_type=self._classify_evidence_type(event),
                        timestamp=ts,
                        data=event.get("data", {}),
                        status=ev_status,
                    )
                )
        return items

    def _assess_event_status(self, control_id: str, event: Dict[str, Any]) -> str:
        """Determine pass/fail/partial for a single piece of evidence."""
        data = event.get("data", {})

        # Encryption checks
        if event.get("type") == "encryption_verification":
            status = data.get("status", "")
            algo = data.get("algorithm", "")
            if status == "verified" and "AES-256-GCM" in algo:
                return "pass"
            if status == "failed" or algo == "none":
                return "fail"
            return "partial"

        # Network / transmission checks
        if event.get("type") == "network_check":
            if data.get("status") == "local_only" and data.get("outbound_connections", 1) == 0:
                return "pass"
            return "partial"

        # Data deletion
        if event.get("type") == "data_deletion":
            return "pass" if data.get("status") == "completed" else "partial"

        # Default: if the event exists and has data, it's a pass
        if data:
            return "pass"
        return "partial"

    def _evaluate_evidence(
        self,
        control_id: str,
        evidence_items: List[EvidenceItem],
        all_events: List[Dict[str, Any]],
    ) -> str:
        """Determine overall status for a control based on its evidence."""
        if not evidence_items:
            return "no_evidence"

        statuses = [e.status for e in evidence_items]
        if all(s == "pass" for s in statuses):
            return "pass"
        if any(s == "fail" for s in statuses):
            return "fail"
        return "partial"

    def _compute_overall_status(self, controls: List[ControlResult]) -> str:
        """Compute overall report status from individual control statuses."""
        statuses = {c.status for c in controls}

        if statuses == {"no_evidence"}:
            return "insufficient_data"
        if "fail" in statuses:
            return "non_compliant"
        if statuses == {"pass"}:
            return "compliant"
        # Mix of pass/partial/no_evidence
        return "partially_compliant"

    def _generate_summary(
        self,
        framework: ComplianceFramework,
        controls: List[ControlResult],
        overall_status: str,
    ) -> str:
        total = len(controls)
        passed = sum(1 for c in controls if c.status == "pass")
        failed = sum(1 for c in controls if c.status == "fail")
        partial = sum(1 for c in controls if c.status == "partial")
        no_ev = sum(1 for c in controls if c.status == "no_evidence")

        parts = [f"{framework.value} compliance assessment: {overall_status}."]
        parts.append(f"{passed}/{total} controls passed.")
        if failed:
            parts.append(f"{failed} controls failed.")
        if partial:
            parts.append(f"{partial} controls partially satisfied.")
        if no_ev:
            parts.append(f"{no_ev} controls had no evidence.")
        return " ".join(parts)

    def _generate_control_notes(
        self, control_id: str, status: str, evidence: List[EvidenceItem]
    ) -> str:
        if status == "no_evidence":
            return "No relevant audit events found for this control."
        if status == "fail":
            failures = [e for e in evidence if e.status == "fail"]
            descs = "; ".join(e.description for e in failures[:3])
            return f"Failing evidence: {descs}"
        if status == "partial":
            return "Some evidence collected but coverage is incomplete."
        return f"Control satisfied with {len(evidence)} evidence item(s)."

    def _describe_event(self, event: Dict[str, Any]) -> str:
        etype = event.get("type", "unknown")
        data = event.get("data", {})
        descriptions = {
            "access_grant": f"Access granted to {data.get('user', '?')} for {data.get('path', '?')}",
            "access_revoke": f"Access revoked for {data.get('user', '?')}",
            "encryption_verification": f"Encryption verification: {data.get('algorithm', '?')} on {data.get('store', '?')}",
            "audit_log_entry": f"Audit log: {data.get('action', '?')} by {data.get('user', '?')} on {data.get('resource', '?')}",
            "destructive_op_confirmed": f"Destructive op '{data.get('operation', '?')}' confirmed by {data.get('confirmed_by', '?')}",
            "data_processing": f"Data processing for '{data.get('purpose', '?')}' at {data.get('location', '?')}",
            "data_deletion": f"Data deletion for subject {data.get('subject', '?')}: {data.get('status', '?')}",
            "sandbox_enforcement": f"Sandbox blocked access to {data.get('path', '?')}",
            "path_grant": f"Path grant to {data.get('user', '?')} for {data.get('path', '?')} ({data.get('scope', '?')})",
            "network_check": f"Network check: {data.get('status', '?')} (outbound: {data.get('outbound_connections', '?')})",
        }
        return descriptions.get(etype, f"Event: {etype}")

    def _classify_evidence_type(self, event: Dict[str, Any]) -> str:
        etype = event.get("type", "")
        config_types = {"encryption_verification", "sandbox_enforcement", "network_check"}
        attestation_types = {"destructive_op_confirmed", "data_deletion"}
        if etype in config_types:
            return "config"
        if etype in attestation_types:
            return "attestation"
        return "log"
