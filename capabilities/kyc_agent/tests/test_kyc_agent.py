"""
Tests for kyc_agent — Indian KYC Document Classification and Verification.

All tests use tmp_path for sandboxed file operations.
Uses pypdf's PdfWriter to create test PDFs with embedded text.
"""

from __future__ import annotations

import os

import pytest
from pypdf import PdfWriter

from capabilities.kyc_agent.agent import (
    _classify_text,
    _infer_type_from_filename,
    _extract_fields_from_text,
    run,
)


# ---------------------------------------------------------------------------
# Helpers — create test PDFs with text content
# ---------------------------------------------------------------------------

def _create_pdf_with_text(path: str, text: str) -> str:
    """Create a minimal PDF containing the given text as a page annotation.

    Since PdfWriter doesn't have a direct add-text-to-page method, we use
    a workaround: create a blank page, then rely on the agent's text
    extraction. For testing, we patch at a higher level or use reportlab.

    For simplicity, we write the text to a .txt sidecar and create a PDF
    that the extract function can read.
    """
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    # Embed text in PDF metadata (custom field) so we have a valid PDF
    writer.add_metadata({"/Subject": text})

    with open(path, "wb") as f:
        writer.write(f)
    return path


def _create_text_pdf(tmp_path, filename: str, text: str) -> str:
    """Create a test PDF. We'll monkeypatch the text extraction in tests."""
    filepath = os.path.join(str(tmp_path), filename)
    _create_pdf_with_text(filepath, text)
    return filepath


# ---------------------------------------------------------------------------
# Unit tests for _classify_text
# ---------------------------------------------------------------------------

class TestClassifyText:
    def test_classify_aadhaar_text(self):
        text = "Unique Identification Authority of India\nUID: 1234 5678 9012\nGovernment of India"
        doc_type, confidence, matches = _classify_text(text)
        assert doc_type == "AADHAAR"
        assert confidence > 0
        assert len(matches) >= 1

    def test_classify_pan_text(self):
        text = "Income Tax Department\nPermanent Account Number\nABCDE1234F\nPAN Card"
        doc_type, confidence, matches = _classify_text(text)
        assert doc_type == "PAN"
        assert confidence > 0
        assert len(matches) >= 1

    def test_classify_passport_text(self):
        text = "Republic of India\nPassport\nPassport No: J1234567\nNationality: Indian\nDate of Birth: 01/01/1990"
        doc_type, confidence, matches = _classify_text(text)
        assert doc_type == "PASSPORT"
        assert confidence > 0
        assert len(matches) >= 2

    def test_classify_voter_id_text(self):
        text = "Election Commission of India\nVoter ID\nEPIC Number: ABC1234567\nElectoral Roll"
        doc_type, confidence, matches = _classify_text(text)
        assert doc_type == "VOTER_ID"
        assert confidence > 0
        assert len(matches) >= 1

    def test_classify_driving_license_text(self):
        text = "Driving Licence\nRegional Transport Authority\nMotor Vehicle Department"
        doc_type, confidence, matches = _classify_text(text)
        assert doc_type == "DRIVING_LICENSE"
        assert confidence > 0
        assert len(matches) >= 1

    def test_classify_unknown_text(self):
        text = "This is just some random text with no KYC patterns at all."
        doc_type, confidence, matches = _classify_text(text)
        assert doc_type == "UNKNOWN"
        assert confidence == 0
        assert matches == []


# ---------------------------------------------------------------------------
# Unit tests for _infer_type_from_filename
# ---------------------------------------------------------------------------

class TestInferTypeFromFilename:
    def test_aadhaar_variants(self):
        assert _infer_type_from_filename("aadhaar_card.pdf") == "AADHAAR"
        assert _infer_type_from_filename("aadhar_front.jpg") == "AADHAAR"
        assert _infer_type_from_filename("uid_scan.pdf") == "AADHAAR"

    def test_pan(self):
        assert _infer_type_from_filename("pan_card.pdf") == "PAN"

    def test_passport(self):
        assert _infer_type_from_filename("passport_scan.pdf") == "PASSPORT"

    def test_voter_id(self):
        assert _infer_type_from_filename("voter_id.pdf") == "VOTER_ID"
        assert _infer_type_from_filename("epic_card.jpg") == "VOTER_ID"

    def test_driving_license(self):
        assert _infer_type_from_filename("driving_license.pdf") == "DRIVING_LICENSE"
        assert _infer_type_from_filename("dl_scan.pdf") == "DRIVING_LICENSE"

    def test_bank_statement(self):
        assert _infer_type_from_filename("bank_statement.pdf") == "BANK_STATEMENT"

    def test_unknown(self):
        assert _infer_type_from_filename("document.pdf") == "UNKNOWN"
        assert _infer_type_from_filename("scan_001.jpg") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Integration tests — classify_document via run()
# ---------------------------------------------------------------------------

class TestClassifyDocument:
    def test_mismatch_detection(self, tmp_path, monkeypatch):
        """File named 'aadhar.pdf' but content is passport text."""
        filepath = _create_text_pdf(tmp_path, "aadhar.pdf", "passport content")

        passport_text = (
            "Republic of India\nPassport\nPassport No: J1234567\n"
            "Nationality: Indian\nDate of Birth: 01/01/1990"
        )
        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            lambda p: passport_text,
        )

        result = run({
            "action": "classify_document",
            "params": {"path": filepath},
            "context": {},
        })

        assert result["status"] == "success"
        assert result["result"]["detected_type"] == "PASSPORT"
        assert result["result"]["expected_type"] == "AADHAAR"
        assert result["result"]["mismatch"] is True
        assert "suggestion" in result["result"]

    def test_classify_pdf_aadhaar(self, tmp_path, monkeypatch):
        filepath = _create_text_pdf(tmp_path, "doc.pdf", "aadhaar")

        aadhaar_text = "Unique Identification Authority\nUID: 1234 5678 9012"
        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            lambda p: aadhaar_text,
        )

        result = run({
            "action": "classify_document",
            "params": {"path": filepath},
            "context": {},
        })

        assert result["status"] == "success"
        assert result["result"]["detected_type"] == "AADHAAR"
        assert result["result"]["confidence"] > 0

    def test_missing_path(self):
        result = run({
            "action": "classify_document",
            "params": {},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "MISSING_PATH"

    def test_file_not_found(self):
        result = run({
            "action": "classify_document",
            "params": {"path": "/nonexistent/doc.pdf"},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "FILE_NOT_FOUND"

    def test_unsupported_format(self, tmp_path):
        txt_file = os.path.join(str(tmp_path), "doc.txt")
        with open(txt_file, "w") as f:
            f.write("test")

        result = run({
            "action": "classify_document",
            "params": {"path": txt_file},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "UNSUPPORTED_FORMAT"


# ---------------------------------------------------------------------------
# classify_batch
# ---------------------------------------------------------------------------

class TestClassifyBatch:
    def test_classify_batch_dry_run(self, tmp_path):
        # Create some test PDFs
        for name in ["aadhaar.pdf", "pan.pdf", "passport.pdf"]:
            _create_text_pdf(tmp_path, name, "test")

        result = run({
            "action": "classify_batch",
            "params": {"path": str(tmp_path)},
            "context": {"dry_run": True},
        })

        assert result["status"] == "success"
        assert "Would classify" in result["action_performed"]
        assert "3" in result["action_performed"]

    def test_classify_batch_folder(self, tmp_path, monkeypatch):
        _create_text_pdf(tmp_path, "aadhaar.pdf", "")
        _create_text_pdf(tmp_path, "pan.pdf", "")

        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            lambda p: "Unique Identification 1234 5678 9012" if "aadhaar" in p else "ABCDE1234F Income Tax",
        )

        result = run({
            "action": "classify_batch",
            "params": {"path": str(tmp_path)},
            "context": {},
        })

        assert result["status"] == "success"
        assert result["result"]["total_files"] == 2
        assert result["result"]["classified"] >= 1


# ---------------------------------------------------------------------------
# extract_kyc_fields
# ---------------------------------------------------------------------------

class TestExtractKycFields:
    def test_extract_aadhaar_fields(self, tmp_path, monkeypatch):
        filepath = _create_text_pdf(tmp_path, "aadhaar.pdf", "")

        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            lambda p: "Name: Raj Kumar\nDOB: 15/06/1990\nUID: 1234 5678 9012\nMale",
        )

        result = run({
            "action": "extract_kyc_fields",
            "params": {"path": filepath, "document_type": "AADHAAR"},
            "context": {},
        })

        assert result["status"] == "success"
        fields = result["result"]["fields"]
        assert fields["uid_number"] == "123456789012"
        assert "name" in fields
        assert fields["gender"] == "Male"

    def test_extract_pan_fields(self, tmp_path, monkeypatch):
        filepath = _create_text_pdf(tmp_path, "pan.pdf", "")

        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            lambda p: "Permanent Account Number\nName: Priya Sharma\nABCDE1234F\nDOB: 10/03/1985",
        )

        result = run({
            "action": "extract_kyc_fields",
            "params": {"path": filepath, "document_type": "PAN"},
            "context": {},
        })

        assert result["status"] == "success"
        fields = result["result"]["fields"]
        assert fields["pan_number"] == "ABCDE1234F"

    def test_missing_type(self, tmp_path):
        filepath = _create_text_pdf(tmp_path, "doc.pdf", "")
        result = run({
            "action": "extract_kyc_fields",
            "params": {"path": filepath},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "MISSING_TYPE"


# ---------------------------------------------------------------------------
# generate_credit_summary
# ---------------------------------------------------------------------------

class TestGenerateCreditSummary:
    def test_generate_summary_standard(self, tmp_path, monkeypatch):
        aadhaar_path = _create_text_pdf(tmp_path, "aadhaar.pdf", "")
        pan_path = _create_text_pdf(tmp_path, "pan.pdf", "")
        bank_path = _create_text_pdf(tmp_path, "bank.pdf", "")

        def fake_extract(path):
            if "aadhaar" in path:
                return "Name: Raj Kumar\n1234 5678 9012\nMale"
            if "pan" in path:
                return "ABCDE1234F\nName: Raj Kumar"
            if "bank" in path:
                return "Account Number: 123456789\nIFSC: SBIN0001234\nBalance"
            return ""

        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            fake_extract,
        )

        result = run({
            "action": "generate_credit_summary",
            "params": {
                "documents": [
                    {"path": aadhaar_path, "type": "AADHAAR"},
                    {"path": pan_path, "type": "PAN"},
                    {"path": bank_path, "type": "BANK_STATEMENT"},
                ],
                "template": "standard",
            },
            "context": {},
        })

        assert result["status"] == "success"
        r = result["result"]
        assert r["identity_verified"] is True
        assert r["address_verified"] is True
        assert "Bank statement present" in r["income_indicators"]
        assert r["kyc_completeness"] == "75%"
        assert r["recommendation"] == "PROCEED_WITH_REVIEW"
        assert "generated_at" in r
        assert len(r["documents_verified"]) == 3
        assert len(r["documents_missing"]) == 1

    def test_generate_summary_incomplete(self):
        result = run({
            "action": "generate_credit_summary",
            "params": {
                "documents": [
                    {"path": "/fake/aadhaar.pdf", "type": "AADHAAR"},
                ],
            },
            "context": {},
        })

        assert result["status"] == "success"
        assert result["result"]["recommendation"] == "INCOMPLETE"
        assert result["result"]["kyc_completeness"] == "25%"

    def test_generate_summary_dry_run(self):
        result = run({
            "action": "generate_credit_summary",
            "params": {
                "documents": [{"path": "/doc.pdf", "type": "AADHAAR"}],
            },
            "context": {"dry_run": True},
        })

        assert result["status"] == "success"
        assert "Would generate" in result["action_performed"]

    def test_missing_documents(self):
        result = run({
            "action": "generate_credit_summary",
            "params": {},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "MISSING_DOCUMENTS"


# ---------------------------------------------------------------------------
# run() entry point
# ---------------------------------------------------------------------------

class TestRunEntryPoint:
    def test_run_dispatches_correctly(self, tmp_path, monkeypatch):
        filepath = _create_text_pdf(tmp_path, "test.pdf", "")
        monkeypatch.setattr(
            "capabilities.kyc_agent.agent._extract_text_from_pdf",
            lambda p: "Unique Identification 1234 5678 9012",
        )

        result = run({
            "action": "classify_document",
            "params": {"path": filepath},
            "context": {},
        })
        assert result["status"] == "success"
        assert "result" in result

    def test_unknown_action(self):
        result = run({
            "action": "nonexistent_action",
            "params": {},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "UNKNOWN_ACTION"


# ---------------------------------------------------------------------------
# check_completeness
# ---------------------------------------------------------------------------

class TestCheckCompleteness:
    def test_complete_home_loan(self, tmp_path, monkeypatch):
        """Folder with Aadhaar, PAN, Bank Statement → 100% complete for home loan."""
        # Create test files
        (tmp_path / "aadhaar.pdf").write_bytes(b"%PDF-1.4 test")
        (tmp_path / "pan_card.pdf").write_bytes(b"%PDF-1.4 test")
        (tmp_path / "bank_statement.pdf").write_bytes(b"%PDF-1.4 test")

        # Patch text extraction to return classifiable text
        texts = {
            "aadhaar.pdf": "Unique Identification Authority aadhaar 1234 5678 9012",
            "pan_card.pdf": "Income Tax Department ABCDE1234F permanent account number",
            "bank_statement.pdf": "Account Statement balance transaction credit debit IFSC branch",
        }
        import capabilities.kyc_agent.agent as kyc
        monkeypatch.setattr(kyc, "_extract_text_from_pdf",
                            lambda fp: texts.get(os.path.basename(fp), ""))

        result = run({
            "action": "check_completeness",
            "params": {"path": str(tmp_path), "loan_type": "home_loan"},
            "context": {"granted_paths": [str(tmp_path)]},
        })
        assert result["status"] == "success"
        assert result["result"]["completeness"] == "100%"
        assert result["result"]["application_status"] == "COMPLETE"
        assert len(result["result"]["missing_required"]) == 0

    def test_incomplete_application(self, tmp_path, monkeypatch):
        """Folder with only Aadhaar → incomplete for home loan."""
        (tmp_path / "aadhaar.pdf").write_bytes(b"%PDF-1.4 test")

        import capabilities.kyc_agent.agent as kyc
        monkeypatch.setattr(kyc, "_extract_text_from_pdf",
                            lambda fp: "Unique Identification Authority aadhaar 1234 5678 9012")

        result = run({
            "action": "check_completeness",
            "params": {"path": str(tmp_path), "loan_type": "home_loan"},
            "context": {"granted_paths": [str(tmp_path)]},
        })
        assert result["status"] == "success"
        assert result["result"]["application_status"] in ("INCOMPLETE", "INSUFFICIENT")
        assert len(result["result"]["missing_required"]) > 0

    def test_dry_run(self, tmp_path):
        result = run({
            "action": "check_completeness",
            "params": {"path": str(tmp_path), "loan_type": "personal_loan"},
            "context": {"granted_paths": [str(tmp_path)], "dry_run": True},
        })
        assert result["status"] == "success"
        assert "preview" in result["result"]

    def test_missing_folder(self):
        result = run({
            "action": "check_completeness",
            "params": {"path": "/nonexistent/folder"},
            "context": {},
        })
        assert result["status"] == "error"

    def test_checklist_structure(self, tmp_path, monkeypatch):
        """Checklist should have required and optional entries."""
        (tmp_path / "pan.pdf").write_bytes(b"%PDF-1.4 test")
        import capabilities.kyc_agent.agent as kyc
        monkeypatch.setattr(kyc, "_extract_text_from_pdf",
                            lambda fp: "Income Tax ABCDE1234F permanent account number")

        result = run({
            "action": "check_completeness",
            "params": {"path": str(tmp_path), "loan_type": "personal_loan"},
            "context": {"granted_paths": [str(tmp_path)]},
        })
        checklist = result["result"]["checklist"]
        assert any(item["required"] for item in checklist)
        assert any(item["present"] for item in checklist)


# ---------------------------------------------------------------------------
# cross_verify
# ---------------------------------------------------------------------------

class TestCrossVerify:
    def test_consistent_documents(self, tmp_path, monkeypatch):
        """Two docs with matching name and DOB → CONSISTENT."""
        (tmp_path / "aadhaar.pdf").write_bytes(b"%PDF-1.4 test")
        (tmp_path / "pan.pdf").write_bytes(b"%PDF-1.4 test")

        texts = {
            "aadhaar.pdf": "Unique Identification aadhaar Rajesh Kumar DOB: 15/06/1990 1234 5678 9012",
            "pan.pdf": "Income Tax ABCDE1234F Rajesh Kumar Date of Birth 15/06/1990",
        }
        import capabilities.kyc_agent.agent as kyc
        monkeypatch.setattr(kyc, "_extract_text_from_pdf",
                            lambda fp: texts.get(os.path.basename(fp), ""))

        result = run({
            "action": "cross_verify",
            "params": {
                "documents": [
                    {"path": str(tmp_path / "aadhaar.pdf"), "type": "AADHAAR"},
                    {"path": str(tmp_path / "pan.pdf"), "type": "PAN"},
                ],
            },
            "context": {"granted_paths": [str(tmp_path)]},
        })
        assert result["status"] == "success"
        assert result["result"]["verification_status"] in ("CONSISTENT", "REVIEW_RECOMMENDED")

    def test_name_mismatch(self, tmp_path, monkeypatch):
        """Two docs with different names → DISCREPANCIES_FOUND.

        We monkeypatch _extract_fields_from_text to simulate name extraction
        since the regex-based extractor needs very specific text formatting.
        """
        (tmp_path / "aadhaar.pdf").write_bytes(b"%PDF-1.4 test")
        (tmp_path / "pan.pdf").write_bytes(b"%PDF-1.4 test")

        texts = {
            "aadhaar.pdf": "Unique Identification aadhaar 1234 5678 9012",
            "pan.pdf": "Income Tax ABCDE1234F",
        }
        import capabilities.kyc_agent.agent as kyc
        monkeypatch.setattr(kyc, "_extract_text_from_pdf",
                            lambda fp: texts.get(os.path.basename(fp), ""))

        # Monkeypatch field extraction to return different names
        original_extract = kyc._extract_fields_from_text
        def mock_extract(text, doc_type):
            fields = original_extract(text, doc_type)
            if "aadhaar" in text:
                fields["name"] = "Rajesh Kumar"
            elif "Income Tax" in text:
                fields["name"] = "Suresh Mehta"
            return fields
        monkeypatch.setattr(kyc, "_extract_fields_from_text", mock_extract)

        result = run({
            "action": "cross_verify",
            "params": {
                "documents": [
                    {"path": str(tmp_path / "aadhaar.pdf"), "type": "AADHAAR"},
                    {"path": str(tmp_path / "pan.pdf"), "type": "PAN"},
                ],
            },
            "context": {"granted_paths": [str(tmp_path)]},
        })
        assert result["status"] == "success"
        assert result["result"]["verification_status"] == "DISCREPANCIES_FOUND"
        assert len(result["result"]["mismatches"]) > 0

    def test_name_variation(self, tmp_path, monkeypatch):
        """'R Kumar' vs 'Rajesh Kumar' → warning, not mismatch."""
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 test")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 test")

        texts = {
            "a.pdf": "Unique Identification aadhaar Rajesh Kumar 1234 5678 9012",
            "b.pdf": "Income Tax ABCDE1234F R Kumar",
        }
        import capabilities.kyc_agent.agent as kyc
        monkeypatch.setattr(kyc, "_extract_text_from_pdf",
                            lambda fp: texts.get(os.path.basename(fp), ""))

        result = run({
            "action": "cross_verify",
            "params": {
                "documents": [
                    {"path": str(tmp_path / "a.pdf"), "type": "AADHAAR"},
                    {"path": str(tmp_path / "b.pdf"), "type": "PAN"},
                ],
            },
            "context": {"granted_paths": [str(tmp_path)]},
        })
        assert result["status"] == "success"
        # Should be a warning or match, not a hard mismatch
        status = result["result"]["verification_status"]
        assert status in ("CONSISTENT", "REVIEW_RECOMMENDED")

    def test_insufficient_documents(self):
        """Less than 2 documents → error."""
        result = run({
            "action": "cross_verify",
            "params": {"documents": [{"path": "/tmp/x.pdf", "type": "AADHAAR"}]},
            "context": {},
        })
        assert result["status"] == "error"
        assert result["error"]["code"] == "INSUFFICIENT_DOCUMENTS"

    def test_dry_run(self):
        result = run({
            "action": "cross_verify",
            "params": {
                "documents": [
                    {"path": "/tmp/a.pdf", "type": "AADHAAR"},
                    {"path": "/tmp/b.pdf", "type": "PAN"},
                ],
            },
            "context": {"dry_run": True},
        })
        assert result["status"] == "success"
        assert "preview" in result["result"]
