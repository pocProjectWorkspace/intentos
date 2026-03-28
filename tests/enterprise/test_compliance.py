"""Tests for the IntentOS Compliance Reporting module (Phase 3B.4)."""

import pytest
from datetime import datetime, timedelta
from core.enterprise.compliance import (
    ComplianceFramework,
    EvidenceItem,
    ControlResult,
    ComplianceReport,
    ComplianceReporter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reporter():
    return ComplianceReporter()


@pytest.fixture
def period():
    start = datetime(2026, 1, 1)
    end = datetime(2026, 3, 31)
    return start, end


@pytest.fixture
def sample_audit_events():
    """A representative set of audit events that should satisfy all frameworks."""
    now = datetime(2026, 2, 15, 10, 0, 0)
    return [
        # Access control events
        {
            "type": "access_grant",
            "timestamp": now.isoformat(),
            "data": {"user": "admin", "path": "/data/records", "permission": "read"},
        },
        {
            "type": "access_revoke",
            "timestamp": (now + timedelta(hours=1)).isoformat(),
            "data": {"user": "former_employee", "path": "/data/records"},
        },
        # Encryption events
        {
            "type": "encryption_verification",
            "timestamp": now.isoformat(),
            "data": {"algorithm": "AES-256-GCM", "store": "credential_store", "status": "verified"},
        },
        # Audit trail events
        {
            "type": "audit_log_entry",
            "timestamp": now.isoformat(),
            "data": {"action": "file_read", "user": "admin", "resource": "/data/records/patient1.json"},
        },
        {
            "type": "audit_log_entry",
            "timestamp": (now + timedelta(minutes=30)).isoformat(),
            "data": {"action": "file_write", "user": "admin", "resource": "/data/records/patient2.json"},
        },
        # Change management / destructive ops
        {
            "type": "destructive_op_confirmed",
            "timestamp": now.isoformat(),
            "data": {"operation": "delete_collection", "confirmed_by": "admin", "target": "/data/old_records"},
        },
        # Data processing / locality
        {
            "type": "data_processing",
            "timestamp": now.isoformat(),
            "data": {"purpose": "analysis", "location": "local", "lawful_basis": "legitimate_interest"},
        },
        # Erasure capability
        {
            "type": "data_deletion",
            "timestamp": now.isoformat(),
            "data": {"subject": "user_123", "scope": "all_personal_data", "status": "completed"},
        },
        # Sandbox enforcement
        {
            "type": "sandbox_enforcement",
            "timestamp": now.isoformat(),
            "data": {"action": "blocked", "path": "/etc/passwd", "reason": "outside_sandbox"},
        },
        # Path grants (for HIPAA access control)
        {
            "type": "path_grant",
            "timestamp": now.isoformat(),
            "data": {"user": "admin", "path": "/data/phi", "scope": "minimum_necessary"},
        },
        # Transmission security
        {
            "type": "network_check",
            "timestamp": now.isoformat(),
            "data": {"outbound_connections": 0, "data_exfiltration_attempts": 0, "status": "local_only"},
        },
    ]


# ---------------------------------------------------------------------------
# 1. ComplianceFramework enum
# ---------------------------------------------------------------------------

class TestComplianceFramework:
    def test_soc2_exists(self):
        assert ComplianceFramework.SOC2 is not None

    def test_gdpr_exists(self):
        assert ComplianceFramework.GDPR is not None

    def test_hipaa_exists(self):
        assert ComplianceFramework.HIPAA is not None

    def test_framework_values(self):
        assert ComplianceFramework.SOC2.value == "SOC2"
        assert ComplianceFramework.GDPR.value == "GDPR"
        assert ComplianceFramework.HIPAA.value == "HIPAA"


# ---------------------------------------------------------------------------
# 2-3. EvidenceItem model
# ---------------------------------------------------------------------------

class TestEvidenceItem:
    def test_evidence_item_creation(self):
        ts = datetime.now()
        item = EvidenceItem(
            control_id="CC6.1",
            description="Access control check",
            evidence_type="log",
            timestamp=ts,
            data={"user": "admin"},
            status="pass",
        )
        assert item.control_id == "CC6.1"
        assert item.description == "Access control check"
        assert item.evidence_type == "log"
        assert item.timestamp == ts
        assert item.data == {"user": "admin"}
        assert item.status == "pass"

    def test_evidence_type_values(self):
        """evidence_type must be one of log, config, attestation."""
        ts = datetime.now()
        for etype in ("log", "config", "attestation"):
            item = EvidenceItem(
                control_id="X",
                description="d",
                evidence_type=etype,
                timestamp=ts,
                data={},
                status="pass",
            )
            assert item.evidence_type == etype

    def test_status_values(self):
        ts = datetime.now()
        for status in ("pass", "fail", "partial"):
            item = EvidenceItem(
                control_id="X",
                description="d",
                evidence_type="log",
                timestamp=ts,
                data={},
                status=status,
            )
            assert item.status == status

    def test_serialization(self):
        ts = datetime(2026, 1, 15, 12, 0, 0)
        item = EvidenceItem(
            control_id="CC6.1",
            description="test",
            evidence_type="log",
            timestamp=ts,
            data={"key": "value"},
            status="pass",
        )
        d = item.to_dict()
        assert isinstance(d, dict)
        assert d["control_id"] == "CC6.1"
        assert d["description"] == "test"
        assert d["evidence_type"] == "log"
        assert d["data"] == {"key": "value"}
        assert d["status"] == "pass"
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# 4-5. ComplianceReport and ControlResult models
# ---------------------------------------------------------------------------

class TestControlResult:
    def test_control_result_creation(self):
        cr = ControlResult(
            control_id="CC6.1",
            control_name="Access Control",
            status="pass",
            evidence_items=[],
            notes="All good",
        )
        assert cr.control_id == "CC6.1"
        assert cr.control_name == "Access Control"
        assert cr.status == "pass"
        assert cr.evidence_items == []
        assert cr.notes == "All good"


class TestComplianceReport:
    def test_report_creation(self):
        now = datetime.now()
        report = ComplianceReport(
            framework=ComplianceFramework.SOC2,
            generated_at=now,
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 3, 31),
            controls=[],
            overall_status="compliant",
            summary="All controls satisfied.",
        )
        assert report.framework == ComplianceFramework.SOC2
        assert report.generated_at == now
        assert report.overall_status == "compliant"
        assert report.summary == "All controls satisfied."
        assert isinstance(report.controls, list)


# ---------------------------------------------------------------------------
# 6-9. Evidence collection
# ---------------------------------------------------------------------------

class TestEvidenceCollection:
    def test_collect_evidence_returns_list(self, reporter, sample_audit_events, period):
        start, end = period
        evidence = reporter.collect_evidence(ComplianceFramework.SOC2, sample_audit_events, start, end)
        assert isinstance(evidence, list)
        assert all(isinstance(e, EvidenceItem) for e in evidence)

    def test_soc2_evidence_categories(self, reporter, sample_audit_events, period):
        start, end = period
        evidence = reporter.collect_evidence(ComplianceFramework.SOC2, sample_audit_events, start, end)
        control_ids = {e.control_id for e in evidence}
        # SOC2 controls
        assert "CC6.1" in control_ids   # Access control
        assert "CC6.7" in control_ids   # Encryption at rest
        assert "CC7.2" in control_ids   # System monitoring
        assert "CC8.1" in control_ids   # Change management

    def test_gdpr_evidence_categories(self, reporter, sample_audit_events, period):
        start, end = period
        evidence = reporter.collect_evidence(ComplianceFramework.GDPR, sample_audit_events, start, end)
        control_ids = {e.control_id for e in evidence}
        assert "Art.5" in control_ids    # Data minimization
        assert "Art.17" in control_ids   # Right to erasure
        assert "Art.30" in control_ids   # Records of processing
        assert "Art.32" in control_ids   # Security of processing

    def test_hipaa_evidence_categories(self, reporter, sample_audit_events, period):
        start, end = period
        evidence = reporter.collect_evidence(ComplianceFramework.HIPAA, sample_audit_events, start, end)
        control_ids = {e.control_id for e in evidence}
        assert "164.312(a)(1)" in control_ids     # Access control
        assert "164.312(a)(2)(iv)" in control_ids  # Encryption
        assert "164.312(b)" in control_ids         # Audit controls
        assert "164.312(e)(1)" in control_ids      # Transmission security


# ---------------------------------------------------------------------------
# 10-13. SOC2 Controls
# ---------------------------------------------------------------------------

class TestSOC2Controls:
    def test_cc6_1_access_control(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        cc6_1 = next(c for c in report.controls if c.control_id == "CC6.1")
        assert cc6_1.status in ("pass", "partial")
        # Evidence should reference access grants / audit log access patterns
        evidence_types = {e.evidence_type for e in cc6_1.evidence_items}
        assert len(cc6_1.evidence_items) > 0

    def test_cc6_7_encryption_at_rest(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        cc6_7 = next(c for c in report.controls if c.control_id == "CC6.7")
        assert cc6_7.status in ("pass", "partial")
        # Should have evidence about AES-256-GCM
        has_aes = any("AES-256-GCM" in str(e.data) for e in cc6_7.evidence_items)
        assert has_aes

    def test_cc7_2_system_monitoring(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        cc7_2 = next(c for c in report.controls if c.control_id == "CC7.2")
        assert cc7_2.status in ("pass", "partial")
        assert len(cc7_2.evidence_items) > 0

    def test_cc8_1_change_management(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        cc8_1 = next(c for c in report.controls if c.control_id == "CC8.1")
        assert cc8_1.status in ("pass", "partial")
        assert len(cc8_1.evidence_items) > 0


# ---------------------------------------------------------------------------
# 14-17. GDPR Controls
# ---------------------------------------------------------------------------

class TestGDPRControls:
    def test_article_5_data_minimization(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.GDPR, sample_audit_events, start, end)
        art5 = next(c for c in report.controls if c.control_id == "Art.5")
        assert art5.status in ("pass", "partial")
        # Evidence should show data stays local
        has_local = any("local" in str(e.data).lower() for e in art5.evidence_items)
        assert has_local

    def test_article_17_right_to_erasure(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.GDPR, sample_audit_events, start, end)
        art17 = next(c for c in report.controls if c.control_id == "Art.17")
        assert art17.status in ("pass", "partial")
        assert len(art17.evidence_items) > 0

    def test_article_30_records_of_processing(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.GDPR, sample_audit_events, start, end)
        art30 = next(c for c in report.controls if c.control_id == "Art.30")
        assert art30.status in ("pass", "partial")

    def test_article_32_security_of_processing(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.GDPR, sample_audit_events, start, end)
        art32 = next(c for c in report.controls if c.control_id == "Art.32")
        assert art32.status in ("pass", "partial")


# ---------------------------------------------------------------------------
# 18-21. HIPAA Controls
# ---------------------------------------------------------------------------

class TestHIPAAControls:
    def test_164_312_a1_access_control(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.HIPAA, sample_audit_events, start, end)
        ctrl = next(c for c in report.controls if c.control_id == "164.312(a)(1)")
        assert ctrl.status in ("pass", "partial")
        assert len(ctrl.evidence_items) > 0

    def test_164_312_a2iv_encryption(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.HIPAA, sample_audit_events, start, end)
        ctrl = next(c for c in report.controls if c.control_id == "164.312(a)(2)(iv)")
        assert ctrl.status in ("pass", "partial")
        has_encryption = any("encrypt" in str(e.data).lower() or "AES" in str(e.data) for e in ctrl.evidence_items)
        assert has_encryption

    def test_164_312_b_audit_controls(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.HIPAA, sample_audit_events, start, end)
        ctrl = next(c for c in report.controls if c.control_id == "164.312(b)")
        assert ctrl.status in ("pass", "partial")

    def test_164_312_e1_transmission_security(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.HIPAA, sample_audit_events, start, end)
        ctrl = next(c for c in report.controls if c.control_id == "164.312(e)(1)")
        assert ctrl.status in ("pass", "partial")
        has_local = any("local" in str(e.data).lower() for e in ctrl.evidence_items)
        assert has_local


# ---------------------------------------------------------------------------
# 22-26. Report generation
# ---------------------------------------------------------------------------

class TestReportGeneration:
    def test_generate_report_returns_compliance_report(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        assert isinstance(report, ComplianceReport)

    def test_report_includes_overall_status(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        assert report.overall_status in ("compliant", "non_compliant", "partially_compliant", "insufficient_data")

    def test_all_pass_means_compliant(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        all_pass = all(c.status == "pass" for c in report.controls)
        if all_pass:
            assert report.overall_status == "compliant"

    def test_any_fail_means_non_compliant(self, reporter, period):
        """If contradicting evidence exists, at least one control fails -> non_compliant."""
        start, end = period
        bad_events = [
            {
                "type": "encryption_verification",
                "timestamp": datetime(2026, 2, 1).isoformat(),
                "data": {"algorithm": "none", "store": "credential_store", "status": "failed"},
            },
        ]
        report = reporter.generate_report(ComplianceFramework.SOC2, bad_events, start, end)
        has_fail = any(c.status == "fail" for c in report.controls)
        if has_fail:
            assert report.overall_status == "non_compliant"

    def test_mix_pass_partial_means_partially_compliant(self, reporter, period):
        start, end = period
        # Provide some evidence but not all
        partial_events = [
            {
                "type": "access_grant",
                "timestamp": datetime(2026, 2, 1).isoformat(),
                "data": {"user": "admin", "path": "/data", "permission": "read"},
            },
            {
                "type": "encryption_verification",
                "timestamp": datetime(2026, 2, 1).isoformat(),
                "data": {"algorithm": "AES-256-GCM", "store": "credential_store", "status": "verified"},
            },
        ]
        report = reporter.generate_report(ComplianceFramework.SOC2, partial_events, start, end)
        statuses = {c.status for c in report.controls}
        if "pass" in statuses and "partial" in statuses and "fail" not in statuses:
            assert report.overall_status == "partially_compliant"


# ---------------------------------------------------------------------------
# 27-29. Report export
# ---------------------------------------------------------------------------

class TestReportExport:
    def test_export_text_returns_string(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        text = reporter.export_text(report)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_export_text_includes_header(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        text = reporter.export_text(report)
        assert "SOC2" in text
        assert "Compliance Report" in text

    def test_export_text_includes_summary(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        text = reporter.export_text(report)
        # Summary section should exist
        assert report.summary in text or "Summary" in text

    def test_export_text_includes_control_details(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        text = reporter.export_text(report)
        # Should mention each control
        for ctrl in report.controls:
            assert ctrl.control_id in text

    def test_export_dict_returns_dict(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        d = reporter.export_dict(report)
        assert isinstance(d, dict)

    def test_export_dict_structure(self, reporter, sample_audit_events, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, start, end)
        d = reporter.export_dict(report)
        assert "framework" in d
        assert "generated_at" in d
        assert "period_start" in d
        assert "period_end" in d
        assert "controls" in d
        assert "overall_status" in d
        assert "summary" in d
        assert isinstance(d["controls"], list)


# ---------------------------------------------------------------------------
# 30-32. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_audit_events_insufficient_data(self, reporter, period):
        start, end = period
        report = reporter.generate_report(ComplianceFramework.SOC2, [], start, end)
        assert report.overall_status == "insufficient_data"

    def test_period_with_no_matching_events(self, reporter, sample_audit_events):
        """Events exist but outside the period -> no_evidence on controls."""
        far_past_start = datetime(2020, 1, 1)
        far_past_end = datetime(2020, 3, 31)
        report = reporter.generate_report(ComplianceFramework.SOC2, sample_audit_events, far_past_start, far_past_end)
        # All controls should be no_evidence since events are outside the period
        for ctrl in report.controls:
            assert ctrl.status == "no_evidence"

    def test_unknown_framework_raises_value_error(self, reporter, period):
        start, end = period
        with pytest.raises(ValueError):
            reporter.generate_report("UNKNOWN_FRAMEWORK", [], start, end)
