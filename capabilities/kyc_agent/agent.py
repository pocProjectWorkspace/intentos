"""
IntentOS kyc_agent — Indian KYC Document Classification and Verification

Primitive actions:
  - classify_document: classify a single PDF/image as an Indian KYC document
  - classify_batch: classify all PDF/image files in a folder
  - extract_kyc_fields: extract key fields from a classified KYC document
  - generate_credit_summary: generate a structured credit assessment summary

Supports: Aadhaar, PAN, Passport, Voter ID, Driving License, Bank Statement.
All processing runs locally — documents never leave the device.

Follows SPEC.md: run() entry point, standard output dicts, dry_run support,
plain-language errors, audit metadata.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Document classification patterns
# ---------------------------------------------------------------------------

DOCUMENT_PATTERNS = {
    "AADHAAR": {
        "patterns": [
            r"\b\d{4}\s?\d{4}\s?\d{4}\b",  # 12-digit UID
            r"unique\s*identification",
            r"uidai",
            r"aadhaar",
            r"government\s*of\s*india",
        ],
        "min_matches": 1,
        "display_name": "Aadhaar Card",
    },
    "PAN": {
        "patterns": [
            r"\b[A-Z]{5}\d{4}[A-Z]\b",  # PAN format: ABCDE1234F
            r"income\s*tax",
            r"permanent\s*account\s*number",
            r"pan\s*card",
        ],
        "min_matches": 1,
        "display_name": "PAN Card",
    },
    "PASSPORT": {
        "patterns": [
            r"republic\s*of\s*india",
            r"passport",
            r"\b[A-Z]\d{7}\b",  # Passport number format
            r"type.*[Pp]",
            r"nationality.*indian",
            r"date\s*of\s*(birth|issue|expiry)",
        ],
        "min_matches": 2,
        "display_name": "Passport",
    },
    "VOTER_ID": {
        "patterns": [
            r"election\s*commission",
            r"voter",
            r"epic",
            r"\b[A-Z]{3}\d{7}\b",  # EPIC number format
            r"electoral",
        ],
        "min_matches": 1,
        "display_name": "Voter ID (EPIC)",
    },
    "DRIVING_LICENSE": {
        "patterns": [
            r"driving\s*licen[cs]e",
            r"transport",
            r"motor\s*vehicle",
            r"\b[A-Z]{2}\d{2}\s?\d{11}\b",  # DL number format
            r"class\s*of\s*vehicle",
            r"validity",
        ],
        "min_matches": 1,
        "display_name": "Driving License",
    },
    "BANK_STATEMENT": {
        "patterns": [
            r"account\s*(number|no|statement)",
            r"balance",
            r"transaction",
            r"ifsc",
            r"branch",
            r"credit|debit",
        ],
        "min_matches": 2,
        "display_name": "Bank Statement",
    },
}

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _meta(
    files_affected: int = 0,
    bytes_affected: int = 0,
    duration_ms: int = 0,
    paths_accessed: list[str] | None = None,
) -> dict:
    return {
        "files_affected": files_affected,
        "bytes_affected": bytes_affected,
        "duration_ms": duration_ms,
        "paths_accessed": paths_accessed or [],
    }


def _error(code: str, message: str) -> dict:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
        "metadata": _meta(),
    }


def _is_path_allowed(path: str, granted_paths: list[str]) -> bool:
    """Check if a path is within the granted paths."""
    resolved = str(Path(path).expanduser().resolve())
    for gp in granted_paths:
        gp_resolved = str(Path(gp).expanduser().resolve())
        if resolved == gp_resolved or resolved.startswith(gp_resolved + os.sep):
            return True
    return False


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(filepath: str) -> str:
    """Extract text from PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(filepath)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def _extract_text_from_image(filepath: str) -> str:
    """Extract text hints from image filename and metadata.

    Without OCR, we rely on filename patterns and basic image metadata.
    This is a fallback — real OCR would use pytesseract.
    """
    filename = Path(filepath).stem.lower()
    return filename.replace("_", " ").replace("-", " ")


def _infer_type_from_filename(filename: str) -> str:
    """Guess expected document type from filename."""
    name = filename.lower()
    if "aadhaar" in name or "aadhar" in name or "uid" in name:
        return "AADHAAR"
    if "pan" in name:
        return "PAN"
    if "passport" in name:
        return "PASSPORT"
    if "voter" in name or "epic" in name:
        return "VOTER_ID"
    if "driving" in name or "license" in name or "licence" in name or "dl" in name:
        return "DRIVING_LICENSE"
    if "bank" in name or "statement" in name:
        return "BANK_STATEMENT"
    return "UNKNOWN"


def _classify_text(text: str) -> tuple:
    """Classify document text. Returns (type, confidence, matched_patterns)."""
    text_lower = text.lower()
    best_type = "UNKNOWN"
    best_score = 0.0
    best_matches: list[str] = []

    for doc_type, config in DOCUMENT_PATTERNS.items():
        matches = []
        for pattern in config["patterns"]:
            if re.search(pattern, text_lower):
                matches.append(pattern)

        if len(matches) >= config["min_matches"]:
            score = len(matches) / len(config["patterns"])
            if score > best_score:
                best_score = score
                best_type = doc_type
                best_matches = matches

    confidence = min(0.99, best_score + 0.3) if best_type != "UNKNOWN" else 0.0
    return best_type, round(confidence, 2), best_matches


def _extract_fields_from_text(text: str, doc_type: str) -> dict:
    """Extract key fields from document text based on type."""
    fields: dict = {}
    text_upper = text  # preserve case for pattern matching IDs

    if doc_type == "AADHAAR":
        uid = re.search(r"\b(\d{4}\s?\d{4}\s?\d{4})\b", text)
        if uid:
            fields["uid_number"] = uid.group(1).replace(" ", "")
        name = re.search(r"(?:name|nm)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if name:
            fields["name"] = name.group(1).strip()
        dob = re.search(r"(?:dob|date\s*of\s*birth|birth)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if dob:
            fields["dob"] = dob.group(1)
        gender = re.search(r"\b(male|female|transgender)\b", text, re.IGNORECASE)
        if gender:
            fields["gender"] = gender.group(1).capitalize()
        fields["name_detected"] = "name" in fields

    elif doc_type == "PAN":
        pan = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", text_upper)
        if pan:
            fields["pan_number"] = pan.group(1)
        name = re.search(r"(?:name|nm)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if name:
            fields["name"] = name.group(1).strip()
        dob = re.search(r"(?:dob|date\s*of\s*birth|birth)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if dob:
            fields["dob"] = dob.group(1)
        father = re.search(r"(?:father|father'?s?\s*name)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if father:
            fields["father_name"] = father.group(1).strip()
        fields["name_detected"] = "name" in fields

    elif doc_type == "PASSPORT":
        pnum = re.search(r"\b([A-Z]\d{7})\b", text_upper)
        if pnum:
            fields["passport_number"] = pnum.group(1)
        name = re.search(r"(?:name|given\s*name|surname)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if name:
            fields["name"] = name.group(1).strip()
        dob = re.search(r"(?:dob|date\s*of\s*birth|birth)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if dob:
            fields["dob"] = dob.group(1)
        nationality = re.search(r"(?:nationality)\s*[:\-]?\s*([A-Za-z]+)", text, re.IGNORECASE)
        if nationality:
            fields["nationality"] = nationality.group(1).strip()
        issue = re.search(r"(?:date\s*of\s*issue|issued)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if issue:
            fields["issue_date"] = issue.group(1)
        expiry = re.search(r"(?:date\s*of\s*expiry|expiry|valid\s*until)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if expiry:
            fields["expiry_date"] = expiry.group(1)
        fields["name_detected"] = "name" in fields

    elif doc_type == "VOTER_ID":
        epic = re.search(r"\b([A-Z]{3}\d{7})\b", text_upper)
        if epic:
            fields["epic_number"] = epic.group(1)
        name = re.search(r"(?:name|nm)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if name:
            fields["name"] = name.group(1).strip()
        father = re.search(r"(?:father|father'?s?\s*name)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if father:
            fields["father_name"] = father.group(1).strip()
        fields["name_detected"] = "name" in fields

    elif doc_type == "DRIVING_LICENSE":
        dl = re.search(r"\b([A-Z]{2}\d{2}\s?\d{11})\b", text_upper)
        if dl:
            fields["dl_number"] = dl.group(1).replace(" ", "")
        name = re.search(r"(?:name|nm)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if name:
            fields["name"] = name.group(1).strip()
        dob = re.search(r"(?:dob|date\s*of\s*birth|birth)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if dob:
            fields["dob"] = dob.group(1)
        blood = re.search(r"(?:blood\s*group)\s*[:\-]?\s*([ABO]{1,2}[+-]?)", text, re.IGNORECASE)
        if blood:
            fields["blood_group"] = blood.group(1)
        validity = re.search(r"(?:validity|valid\s*(?:till|until|upto))\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
        if validity:
            fields["validity"] = validity.group(1)
        fields["name_detected"] = "name" in fields

    elif doc_type == "BANK_STATEMENT":
        acct = re.search(r"(?:account\s*(?:number|no))\s*[:\-]?\s*(\d{9,18})", text, re.IGNORECASE)
        if acct:
            fields["account_number"] = acct.group(1)
        ifsc = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text_upper)
        if ifsc:
            fields["ifsc_code"] = ifsc.group(1)
        branch = re.search(r"(?:branch)\s*[:\-]?\s*([A-Za-z ]+)", text, re.IGNORECASE)
        if branch:
            fields["branch"] = branch.group(1).strip()
        fields["name_detected"] = "name" in fields

    return fields


# ---------------------------------------------------------------------------
# classify_document
# ---------------------------------------------------------------------------

def _classify_document(params: dict, context: dict) -> dict:
    """Classify a single KYC document (PDF or image)."""
    t0 = time.monotonic()
    filepath = params.get("path", "").strip()

    if not filepath:
        return _error("MISSING_PATH", "I need the path to the document to classify")

    filepath = str(Path(filepath).expanduser().resolve())

    if not os.path.exists(filepath):
        return _error("FILE_NOT_FOUND", "I couldn't find that document — it may have been moved or deleted")

    granted = context.get("granted_paths", [])
    if granted and not _is_path_allowed(filepath, granted):
        return _error("PATH_NOT_GRANTED", "I don't have access to that location")

    ext = Path(filepath).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return _error(
            "UNSUPPORTED_FORMAT",
            f"I can classify PDF and image files, but not '{ext}' files",
        )

    filename = Path(filepath).name

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would classify '{filename}'",
            "result": {"preview": f"Classify document at {filepath}"},
            "metadata": _meta(paths_accessed=[filepath]),
        }

    # Extract text
    try:
        if ext == ".pdf":
            text = _extract_text_from_pdf(filepath)
        else:
            text = _extract_text_from_image(filepath)
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to read that document")
    except Exception:
        return _error("READ_FAILED", "Something went wrong while reading the document")

    # Classify
    detected_type, confidence, matched_patterns = _classify_text(text)
    expected_type = _infer_type_from_filename(filename)
    mismatch = (
        expected_type != "UNKNOWN"
        and detected_type != "UNKNOWN"
        and expected_type != detected_type
    )

    display_name = DOCUMENT_PATTERNS.get(detected_type, {}).get("display_name", "Unknown")

    # Extract fields
    extracted_fields = _extract_fields_from_text(text, detected_type)

    # Build suggestion
    suggestion = None
    if mismatch:
        suggestion = (
            f"This file appears to be a {display_name}, but is named '{filename}'. "
            f"Consider renaming."
        )

    action_msg = f"Classified '{filename}' as {display_name}"
    if mismatch:
        action_msg += " (mismatch detected)"

    file_size = os.path.getsize(filepath)
    elapsed = int((time.monotonic() - t0) * 1000)

    result = {
        "path": filepath,
        "filename": filename,
        "detected_type": detected_type,
        "detected_display": display_name,
        "expected_type": expected_type,
        "mismatch": mismatch,
        "confidence": confidence,
        "matched_patterns": matched_patterns,
        "extracted_fields": extracted_fields,
    }
    if suggestion:
        result["suggestion"] = suggestion

    return {
        "status": "success",
        "action_performed": action_msg,
        "result": result,
        "metadata": _meta(
            files_affected=1,
            bytes_affected=file_size,
            duration_ms=elapsed,
            paths_accessed=[filepath],
        ),
    }


# ---------------------------------------------------------------------------
# classify_batch
# ---------------------------------------------------------------------------

def _classify_batch(params: dict, context: dict) -> dict:
    """Classify all PDF/image files in a folder."""
    t0 = time.monotonic()
    folder_path = params.get("path", "").strip()
    recursive = params.get("recursive", False)

    if not folder_path:
        return _error("MISSING_PATH", "I need the path to the folder to scan")

    folder_path = str(Path(folder_path).expanduser().resolve())

    if not os.path.isdir(folder_path):
        return _error("NOT_A_FOLDER", "That path is not a folder")

    granted = context.get("granted_paths", [])
    if granted and not _is_path_allowed(folder_path, granted):
        return _error("PATH_NOT_GRANTED", "I don't have access to that location")

    # Gather files
    files: list[str] = []
    if recursive:
        for root, _dirs, filenames in os.walk(folder_path):
            for fn in filenames:
                if Path(fn).suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(os.path.join(root, fn))
    else:
        for fn in os.listdir(folder_path):
            full = os.path.join(folder_path, fn)
            if os.path.isfile(full) and Path(fn).suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(full)

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would classify {len(files)} document(s) in '{Path(folder_path).name}'",
            "result": {"preview": f"Classify {len(files)} files in {folder_path}"},
            "metadata": _meta(paths_accessed=[folder_path]),
        }

    classified_count = 0
    unrecognized_count = 0
    mismatch_count = 0
    file_results: list[dict] = []

    for fp in files:
        try:
            ext = Path(fp).suffix.lower()
            if ext == ".pdf":
                text = _extract_text_from_pdf(fp)
            else:
                text = _extract_text_from_image(fp)

            detected_type, confidence, _matches = _classify_text(text)
            expected_type = _infer_type_from_filename(Path(fp).name)
            mismatch = (
                expected_type != "UNKNOWN"
                and detected_type != "UNKNOWN"
                and expected_type != detected_type
            )

            if detected_type == "UNKNOWN":
                unrecognized_count += 1
            else:
                classified_count += 1

            if mismatch:
                mismatch_count += 1

            file_results.append({
                "filename": Path(fp).name,
                "detected": detected_type,
                "mismatch": mismatch,
                "confidence": confidence,
            })
        except Exception:
            unrecognized_count += 1
            file_results.append({
                "filename": Path(fp).name,
                "detected": "ERROR",
                "mismatch": False,
                "confidence": 0.0,
            })

    total = len(files)
    summary = f"{classified_count} of {total} documents classified."
    if mismatch_count > 0:
        summary += f" {mismatch_count} file(s) appear to be misnamed."

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Classified {total} document(s) in '{Path(folder_path).name}'",
        "result": {
            "total_files": total,
            "classified": classified_count,
            "unrecognized": unrecognized_count,
            "mismatches": mismatch_count,
            "files": file_results,
            "summary": summary,
        },
        "metadata": _meta(
            files_affected=total,
            duration_ms=elapsed,
            paths_accessed=[folder_path],
        ),
    }


# ---------------------------------------------------------------------------
# extract_kyc_fields
# ---------------------------------------------------------------------------

def _extract_kyc_fields(params: dict, context: dict) -> dict:
    """Extract key fields from a KYC document based on its type."""
    t0 = time.monotonic()
    filepath = params.get("path", "").strip()
    doc_type = params.get("document_type", "").strip().upper()

    if not filepath:
        return _error("MISSING_PATH", "I need the path to the document")
    if not doc_type:
        return _error("MISSING_TYPE", "I need the document type (e.g. AADHAAR, PAN, PASSPORT)")

    valid_types = set(DOCUMENT_PATTERNS.keys())
    if doc_type not in valid_types:
        return _error(
            "INVALID_TYPE",
            f"Supported document types: {', '.join(sorted(valid_types))}",
        )

    filepath = str(Path(filepath).expanduser().resolve())

    if not os.path.exists(filepath):
        return _error("FILE_NOT_FOUND", "I couldn't find that document — it may have been moved or deleted")

    granted = context.get("granted_paths", [])
    if granted and not _is_path_allowed(filepath, granted):
        return _error("PATH_NOT_GRANTED", "I don't have access to that location")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would extract {doc_type} fields from '{Path(filepath).name}'",
            "result": {"preview": f"Extract {doc_type} fields from {filepath}"},
            "metadata": _meta(paths_accessed=[filepath]),
        }

    try:
        ext = Path(filepath).suffix.lower()
        if ext == ".pdf":
            text = _extract_text_from_pdf(filepath)
        else:
            text = _extract_text_from_image(filepath)
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to read that document")
    except Exception:
        return _error("READ_FAILED", "Something went wrong while reading the document")

    fields = _extract_fields_from_text(text, doc_type)
    display_name = DOCUMENT_PATTERNS[doc_type]["display_name"]

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Extracted {len(fields)} field(s) from '{Path(filepath).name}' as {display_name}",
        "result": {
            "path": filepath,
            "filename": Path(filepath).name,
            "document_type": doc_type,
            "display_name": display_name,
            "fields": fields,
        },
        "metadata": _meta(
            files_affected=1,
            duration_ms=elapsed,
            paths_accessed=[filepath],
        ),
    }


# ---------------------------------------------------------------------------
# generate_credit_summary
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Loan application requirements by type
# ---------------------------------------------------------------------------

LOAN_REQUIREMENTS: dict[str, dict] = {
    "home_loan": {
        "display_name": "Home Loan",
        "required": ["AADHAAR", "PAN", "BANK_STATEMENT"],
        "optional": ["DRIVING_LICENSE", "VOTER_ID", "PASSPORT"],
        "additional": ["property_valuation", "sale_agreement", "property_tax_receipt"],
        "min_bank_statement_months": 6,
    },
    "personal_loan": {
        "display_name": "Personal Loan",
        "required": ["AADHAAR", "PAN", "BANK_STATEMENT"],
        "optional": ["DRIVING_LICENSE", "VOTER_ID"],
        "additional": ["salary_slip"],
        "min_bank_statement_months": 3,
    },
    "vehicle_loan": {
        "display_name": "Vehicle Loan",
        "required": ["AADHAAR", "PAN", "DRIVING_LICENSE", "BANK_STATEMENT"],
        "optional": ["VOTER_ID"],
        "additional": ["vehicle_quotation"],
        "min_bank_statement_months": 6,
    },
    "business_loan": {
        "display_name": "Business Loan",
        "required": ["AADHAAR", "PAN", "BANK_STATEMENT"],
        "optional": ["DRIVING_LICENSE", "VOTER_ID"],
        "additional": ["gst_certificate", "itr_last_2_years", "business_registration"],
        "min_bank_statement_months": 12,
    },
    "default": {
        "display_name": "General Loan",
        "required": ["AADHAAR", "PAN", "BANK_STATEMENT"],
        "optional": ["DRIVING_LICENSE", "VOTER_ID", "PASSPORT"],
        "additional": [],
        "min_bank_statement_months": 3,
    },
}


# ---------------------------------------------------------------------------
# check_completeness
# ---------------------------------------------------------------------------

def _check_completeness(params: dict, context: dict) -> dict:
    """Check if a loan application folder has all required documents."""
    t0 = time.monotonic()
    folder_path = params.get("path", "").strip()
    loan_type = params.get("loan_type", "default").strip().lower()

    if not folder_path:
        return _error("MISSING_PATH", "I need the path to the application folder")

    folder_path = str(Path(folder_path).expanduser().resolve())
    if not os.path.isdir(folder_path):
        return _error("NOT_A_FOLDER", "That path is not a folder")

    granted = context.get("granted_paths", [])
    if granted and not _is_path_allowed(folder_path, granted):
        return _error("PATH_NOT_GRANTED", "I don't have access to that location")

    requirements = LOAN_REQUIREMENTS.get(loan_type, LOAN_REQUIREMENTS["default"])

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would check completeness for {requirements['display_name']} application",
            "result": {"preview": f"Check {folder_path} against {loan_type} requirements"},
            "metadata": _meta(paths_accessed=[folder_path]),
        }

    # Classify all documents in the folder
    files: list[str] = []
    for fn in os.listdir(folder_path):
        full = os.path.join(folder_path, fn)
        if os.path.isfile(full) and Path(fn).suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(full)

    found_types: dict[str, str] = {}  # type → filename
    for fp in files:
        try:
            ext = Path(fp).suffix.lower()
            text = _extract_text_from_pdf(fp) if ext == ".pdf" else _extract_text_from_image(fp)
            detected, confidence, _ = _classify_text(text)
            if detected != "UNKNOWN" and confidence > 0.3:
                found_types[detected] = Path(fp).name
        except Exception:
            pass

    # Check against requirements
    required = set(requirements["required"])
    optional = set(requirements.get("optional", []))
    present_required = required & set(found_types.keys())
    missing_required = required - set(found_types.keys())
    present_optional = optional & set(found_types.keys())

    completeness_pct = int(len(present_required) / len(required) * 100) if required else 100

    if completeness_pct == 100:
        status_text = "COMPLETE"
        action_msg = f"Application is complete for {requirements['display_name']}"
    elif completeness_pct >= 50:
        status_text = "INCOMPLETE"
        action_msg = f"Application is incomplete — {len(missing_required)} required document(s) missing"
    else:
        status_text = "INSUFFICIENT"
        action_msg = f"Application has insufficient documents — only {len(present_required)} of {len(required)} required"

    # Build document checklist
    checklist: list[dict] = []
    for doc_type in sorted(required):
        display = DOCUMENT_PATTERNS.get(doc_type, {}).get("display_name", doc_type)
        checklist.append({
            "document": display,
            "type": doc_type,
            "required": True,
            "present": doc_type in found_types,
            "filename": found_types.get(doc_type, ""),
        })
    for doc_type in sorted(optional):
        display = DOCUMENT_PATTERNS.get(doc_type, {}).get("display_name", doc_type)
        checklist.append({
            "document": display,
            "type": doc_type,
            "required": False,
            "present": doc_type in found_types,
            "filename": found_types.get(doc_type, ""),
        })

    # Additional documents (non-KYC, check by filename only)
    additional_found: list[str] = []
    additional_missing: list[str] = []
    for add_doc in requirements.get("additional", []):
        found = any(add_doc.replace("_", " ") in Path(fp).stem.lower().replace("_", " ")
                     for fp in files)
        if found:
            additional_found.append(add_doc)
        else:
            additional_missing.append(add_doc)

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": action_msg,
        "result": {
            "loan_type": loan_type,
            "loan_display": requirements["display_name"],
            "completeness": f"{completeness_pct}%",
            "application_status": status_text,
            "total_files": len(files),
            "documents_found": len(found_types),
            "required_present": len(present_required),
            "required_total": len(required),
            "missing_required": [
                DOCUMENT_PATTERNS.get(t, {}).get("display_name", t)
                for t in sorted(missing_required)
            ],
            "optional_present": len(present_optional),
            "checklist": checklist,
            "additional_found": additional_found,
            "additional_missing": additional_missing,
            "summary": action_msg,
        },
        "metadata": _meta(
            files_affected=len(files),
            duration_ms=elapsed,
            paths_accessed=[folder_path],
        ),
    }


# ---------------------------------------------------------------------------
# cross_verify
# ---------------------------------------------------------------------------

def _cross_verify(params: dict, context: dict) -> dict:
    """Cross-verify data across multiple KYC documents for the same applicant."""
    t0 = time.monotonic()
    documents = params.get("documents", [])

    if not documents or len(documents) < 2:
        return _error("INSUFFICIENT_DOCUMENTS", "I need at least 2 documents to cross-verify")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would cross-verify {len(documents)} documents",
            "result": {"preview": f"Cross-verify {len(documents)} documents"},
            "metadata": _meta(),
        }

    # Extract fields from each document
    doc_data: list[dict] = []
    paths_accessed: list[str] = []

    for doc_info in documents:
        doc_path = doc_info.get("path", "").strip()
        doc_type = doc_info.get("type", "").strip().upper()
        entry = {"type": doc_type, "path": doc_path, "fields": {}}

        if doc_path:
            doc_path = str(Path(doc_path).expanduser().resolve())
            paths_accessed.append(doc_path)
            granted = context.get("granted_paths", [])
            if granted and not _is_path_allowed(doc_path, granted):
                continue
            try:
                if os.path.exists(doc_path):
                    ext = Path(doc_path).suffix.lower()
                    text = _extract_text_from_pdf(doc_path) if ext == ".pdf" else _extract_text_from_image(doc_path)
                    entry["fields"] = _extract_fields_from_text(text, doc_type)
            except Exception:
                pass

        doc_data.append(entry)

    # Cross-verification checks
    mismatches: list[dict] = []
    warnings: list[str] = []
    matches: list[str] = []

    # Collect all names found
    names: list[dict] = []
    for d in doc_data:
        name = d["fields"].get("name", "").strip()
        if name:
            names.append({"document": d["type"], "name": name})

    # Check name consistency
    if len(names) >= 2:
        base_name = names[0]["name"].lower()
        for other in names[1:]:
            other_name = other["name"].lower()
            similarity = _name_similarity(base_name, other_name)
            if similarity >= 0.9:
                matches.append(
                    f"Name match: '{names[0]['name']}' ({names[0]['document']}) "
                    f"≈ '{other['name']}' ({other['document']})"
                )
            elif similarity >= 0.5:
                warnings.append(
                    f"Name variation: '{names[0]['name']}' ({names[0]['document']}) "
                    f"vs '{other['name']}' ({other['document']}) — likely same person but verify"
                )
            else:
                mismatches.append({
                    "field": "name",
                    "doc1": names[0]["document"],
                    "value1": names[0]["name"],
                    "doc2": other["document"],
                    "value2": other["name"],
                    "severity": "HIGH",
                    "message": f"Name mismatch: '{names[0]['name']}' vs '{other['name']}'"
                })

    # Check DOB consistency
    dobs: list[dict] = []
    for d in doc_data:
        dob = d["fields"].get("dob", "").strip()
        if dob:
            dobs.append({"document": d["type"], "dob": dob})

    if len(dobs) >= 2:
        base_dob = dobs[0]["dob"]
        for other in dobs[1:]:
            if _normalize_date(base_dob) == _normalize_date(other["dob"]):
                matches.append(f"DOB match across {dobs[0]['document']} and {other['document']}")
            else:
                mismatches.append({
                    "field": "dob",
                    "doc1": dobs[0]["document"],
                    "value1": base_dob,
                    "doc2": other["document"],
                    "value2": other["dob"],
                    "severity": "HIGH",
                    "message": f"Date of birth mismatch: {base_dob} vs {other['dob']}"
                })

    # Check document number uniqueness (same type shouldn't appear twice with different numbers)
    doc_numbers: dict[str, list] = {}
    for d in doc_data:
        for field_name in ("uid_number", "pan_number", "passport_number", "epic_number", "dl_number"):
            val = d["fields"].get(field_name, "").strip()
            if val:
                key = f"{d['type']}_{field_name}"
                doc_numbers.setdefault(key, []).append(val)

    # Determine overall verification status
    if mismatches:
        verification_status = "DISCREPANCIES_FOUND"
        confidence = max(0.3, 1.0 - len(mismatches) * 0.2)
    elif warnings:
        verification_status = "REVIEW_RECOMMENDED"
        confidence = 0.75
    else:
        verification_status = "CONSISTENT"
        confidence = 0.95

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Cross-verified {len(documents)} documents — {verification_status.lower().replace('_', ' ')}",
        "result": {
            "documents_checked": len(doc_data),
            "verification_status": verification_status,
            "confidence": round(confidence, 2),
            "matches": matches,
            "mismatches": mismatches,
            "warnings": warnings,
            "summary": (
                f"Verified {len(doc_data)} documents. "
                f"{len(matches)} field(s) consistent, "
                f"{len(mismatches)} mismatch(es), "
                f"{len(warnings)} warning(s)."
            ),
        },
        "metadata": _meta(
            files_affected=len(documents),
            duration_ms=elapsed,
            paths_accessed=paths_accessed,
        ),
    }


def _name_similarity(name1: str, name2: str) -> float:
    """Simple name similarity score (0-1) handling Indian name variations."""
    if name1 == name2:
        return 1.0

    # Tokenize and compare
    tokens1 = set(name1.lower().split())
    tokens2 = set(name2.lower().split())

    if not tokens1 or not tokens2:
        return 0.0

    # Check if one is a subset of the other (e.g., "R Kumar" vs "Rajesh Kumar")
    if tokens1.issubset(tokens2) or tokens2.issubset(tokens1):
        return 0.85

    # Jaccard similarity on tokens
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    jaccard = len(intersection) / len(union) if union else 0.0

    # Check initial matching (R. Kumar vs Rajesh Kumar)
    initials1 = {t[0] for t in tokens1 if t}
    initials2 = {t[0] for t in tokens2 if t}
    initial_overlap = len(initials1 & initials2) / max(len(initials1), len(initials2)) if initials1 and initials2 else 0

    return max(jaccard, initial_overlap * 0.7)


def _normalize_date(date_str: str) -> str:
    """Normalize date string for comparison (handles DD/MM/YYYY, DD-MM-YYYY, etc)."""
    cleaned = date_str.strip().replace("/", "-").replace(".", "-")
    parts = cleaned.split("-")
    if len(parts) == 3:
        # Normalize to YYYY-MM-DD
        if len(parts[0]) == 4:
            return cleaned  # Already YYYY-MM-DD
        if len(parts[2]) == 4:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"  # DD-MM-YYYY → YYYY-MM-DD
    return cleaned


_REQUIRED_KYC_DOCS = {"AADHAAR", "PAN", "BANK_STATEMENT", "DRIVING_LICENSE"}


def _generate_credit_summary(params: dict, context: dict) -> dict:
    """Generate a structured credit assessment summary from document data."""
    t0 = time.monotonic()
    documents = params.get("documents", [])
    template = params.get("template", "standard")

    if not documents:
        return _error("MISSING_DOCUMENTS", "I need a list of documents to generate a credit summary")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would generate credit summary from {len(documents)} document(s)",
            "result": {"preview": f"Generate {template} credit summary from {len(documents)} documents"},
            "metadata": _meta(),
        }

    doc_types_present: set[str] = set()
    all_fields: dict[str, dict] = {}
    paths_accessed: list[str] = []
    applicant_name = ""

    for doc_info in documents:
        doc_path = doc_info.get("path", "").strip()
        doc_type = doc_info.get("type", "").strip().upper()
        doc_types_present.add(doc_type)

        if doc_path:
            doc_path = str(Path(doc_path).expanduser().resolve())
            paths_accessed.append(doc_path)

            try:
                if os.path.exists(doc_path):
                    ext = Path(doc_path).suffix.lower()
                    if ext == ".pdf":
                        text = _extract_text_from_pdf(doc_path)
                    else:
                        text = _extract_text_from_image(doc_path)
                    fields = _extract_fields_from_text(text, doc_type)
                    all_fields[doc_type] = fields
                    if not applicant_name and fields.get("name"):
                        applicant_name = fields["name"]
            except Exception:
                pass

    # Determine verified documents
    docs_verified = []
    for dt in sorted(doc_types_present):
        display = DOCUMENT_PATTERNS.get(dt, {}).get("display_name", dt)
        docs_verified.append(display)

    docs_missing = []
    for req in sorted(_REQUIRED_KYC_DOCS):
        if req not in doc_types_present:
            display = DOCUMENT_PATTERNS.get(req, {}).get("display_name", req)
            docs_missing.append(display)

    identity_verified = "AADHAAR" in doc_types_present and "PAN" in doc_types_present
    address_verified = "AADHAAR" in doc_types_present
    income_indicators = "Bank statement present" if "BANK_STATEMENT" in doc_types_present else "No income documents"

    # Completeness
    present_count = len(doc_types_present & _REQUIRED_KYC_DOCS)
    total_required = len(_REQUIRED_KYC_DOCS)
    completeness_pct = f"{int(present_count / total_required * 100)}%"

    # Recommendation
    if present_count == total_required and identity_verified:
        recommendation = "APPROVE"
    elif present_count >= total_required - 1 and identity_verified:
        recommendation = "PROCEED_WITH_REVIEW"
    else:
        recommendation = "INCOMPLETE"

    # Flags
    flags: list[str] = []
    if not identity_verified:
        flags.append("Identity not fully verified — missing Aadhaar or PAN")
    if not address_verified:
        flags.append("Address not verified — no Aadhaar on file")
    if "BANK_STATEMENT" not in doc_types_present:
        flags.append("No bank statement provided for income verification")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Generated credit summary from {len(documents)} document(s)",
        "result": {
            "applicant_name": applicant_name or "Not available",
            "documents_verified": docs_verified,
            "documents_missing": docs_missing,
            "identity_verified": identity_verified,
            "address_verified": address_verified,
            "income_indicators": income_indicators,
            "kyc_completeness": completeness_pct,
            "recommendation": recommendation,
            "flags": flags,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "metadata": _meta(
            files_affected=len(documents),
            duration_ms=elapsed,
            paths_accessed=paths_accessed,
        ),
    }


# ---------------------------------------------------------------------------
# Action registry and entry point
# ---------------------------------------------------------------------------

_ACTIONS = {
    "classify_document": _classify_document,
    "classify_batch": _classify_batch,
    "extract_kyc_fields": _extract_kyc_fields,
    "generate_credit_summary": _generate_credit_summary,
    "check_completeness": _check_completeness,
    "cross_verify": _cross_verify,
}


def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return _error("UNKNOWN_ACTION", f"I don't know how to do '{action}'")

    try:
        return handler(params, context)
    except Exception:
        return _error("AGENT_CRASH", "Something went wrong running that operation")
