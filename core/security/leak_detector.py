"""
IntentOS Leak Detection Pipeline.

Scans text and structured agent output for credentials, API keys,
private keys, auth tokens, and high-entropy secrets. All processing
happens locally — nothing leaves the device.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.security.exceptions import LeakDetectedError


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"


class Action(Enum):
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CredentialPattern:
    """A single credential detection pattern."""
    name: str
    prefix_hint: str          # Fast pre-filter before regex
    regex: re.Pattern
    severity: Severity
    action: Action


@dataclass(frozen=True)
class LeakDetection:
    """A single detection result."""
    pattern_name: str
    severity: Severity
    action: Action
    matched_text: str         # First 10 chars + "..."
    start_pos: int
    end_pos: int


@dataclass
class ScanResult:
    """Result of scan_agent_output()."""
    detections: List[LeakDetection] = field(default_factory=list)
    sanitized: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

def _build_patterns() -> List[CredentialPattern]:
    """Build and compile all credential detection patterns."""

    def p(name: str, hint: str, pattern: str, severity: Severity, action: Action) -> CredentialPattern:
        return CredentialPattern(
            name=name,
            prefix_hint=hint,
            regex=re.compile(pattern),
            severity=severity,
            action=action,
        )

    return [
        # --- API Keys (Critical / Block) ---
        p("anthropic_api_key", "sk-ant-",
          r"sk-ant-api[a-zA-Z0-9\-_]{20,}",
          Severity.CRITICAL, Action.BLOCK),

        p("openai_api_key", "sk-",
          r"(?<![a-zA-Z])sk-proj-[a-zA-Z0-9]{20,}",
          Severity.CRITICAL, Action.BLOCK),

        p("openai_api_key_generic", "sk-",
          r"(?<![a-zA-Z])sk-[a-zA-Z0-9]{40,}",
          Severity.CRITICAL, Action.BLOCK),

        p("aws_access_key", "AKIA",
          r"AKIA[0-9A-Z]{16}",
          Severity.CRITICAL, Action.BLOCK),

        p("github_pat", "ghp_",
          r"ghp_[a-zA-Z0-9]{36}",
          Severity.CRITICAL, Action.BLOCK),

        # --- API Keys (High / Redact) ---
        p("github_oauth", "gho_",
          r"gho_[a-zA-Z0-9]{36}",
          Severity.HIGH, Action.REDACT),

        p("github_app", "ghs_",
          r"ghs_[a-zA-Z0-9]{36}",
          Severity.HIGH, Action.REDACT),

        p("google_api_key", "AIza",
          r"AIza[0-9A-Za-z_\-]{35}",
          Severity.HIGH, Action.REDACT),

        p("slack_token", "xox",
          r"xox[bpsa]-[0-9a-zA-Z\-]{10,}",
          Severity.HIGH, Action.REDACT),

        p("sendgrid_key", "SG.",
          r"SG\.[a-zA-Z0-9_\-]{22}\.[a-zA-Z0-9_\-]{43}",
          Severity.HIGH, Action.REDACT),

        # --- Private Keys (Critical / Block) ---
        p("openssh_private_key", "-----BEGIN OPENSSH",
          r"-----BEGIN OPENSSH PRIVATE KEY-----",
          Severity.CRITICAL, Action.BLOCK),

        p("pem_private_key", "-----BEGIN",
          r"-----BEGIN\s+(?:RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----",
          Severity.CRITICAL, Action.BLOCK),

        # --- Auth Tokens (High / Redact) ---
        p("bearer_token", "Bearer ",
          r"Bearer\s+[a-zA-Z0-9._\-]{20,}",
          Severity.HIGH, Action.REDACT),

        p("basic_auth", "Basic ",
          r"Basic\s+[a-zA-Z0-9+/=]{20,}",
          Severity.HIGH, Action.REDACT),

        p("aws_signature", "AWS4-HMAC",
          r"AWS4-HMAC-SHA256\s+Credential=[^\s]+",
          Severity.HIGH, Action.REDACT),

        # --- High-Entropy (Medium / Warn) ---
        p("high_entropy_hex", "",
          r"(?<![a-zA-Z0-9])[0-9a-f]{40,}(?![a-zA-Z0-9])",
          Severity.MEDIUM, Action.WARN),
    ]


# ---------------------------------------------------------------------------
# LeakDetector
# ---------------------------------------------------------------------------

class LeakDetector:
    """Scans text for leaked credentials and secrets."""

    def __init__(self, patterns: Optional[List[CredentialPattern]] = None):
        self._patterns = patterns or _build_patterns()

    # -- Public API --

    def scan(self, text: Optional[str]) -> List[LeakDetection]:
        """Scan text for leaked credentials. Returns list of LeakDetection."""
        if not text:
            return []

        detections: List[LeakDetection] = []

        for pattern in self._patterns:
            # Fast pre-filter: skip regex if hint not present
            if pattern.prefix_hint and pattern.prefix_hint not in text:
                continue

            for match in pattern.regex.finditer(text):
                matched = match.group(0)
                truncated = matched[:10] + "..." if len(matched) > 10 else matched
                detections.append(LeakDetection(
                    pattern_name=pattern.name,
                    severity=pattern.severity,
                    action=pattern.action,
                    matched_text=truncated,
                    start_pos=match.start(),
                    end_pos=match.end(),
                ))

        return detections

    def scan_agent_output(self, output: Dict[str, Any]) -> ScanResult:
        """Recursively scan all string values in a nested dict.

        Returns a ScanResult with all detections and a sanitized copy
        of the dict where secrets are redacted.
        """
        all_detections: List[LeakDetection] = []
        sanitized = self._walk_and_scan(output, all_detections)
        return ScanResult(detections=all_detections, sanitized=sanitized)

    def redact(self, text: Optional[str]) -> str:
        """Replace all detected secrets with [REDACTED:{pattern_name}]."""
        if not text:
            return ""

        detections = self.scan(text)
        if not detections:
            return text

        # Sort by start position descending so replacements don't shift indices
        detections.sort(key=lambda d: d.start_pos, reverse=True)

        result = text
        for d in detections:
            replacement = f"[REDACTED:{d.pattern_name}]"
            result = result[:d.start_pos] + replacement + result[d.end_pos:]

        return result

    # -- Private helpers --

    def _walk_and_scan(self, obj: Any, detections: List[LeakDetection]) -> Any:
        """Recursively walk a structure, scan strings, return sanitized copy."""
        if obj is None:
            return None

        if isinstance(obj, str):
            found = self.scan(obj)
            detections.extend(found)
            if found:
                return self.redact(obj)
            return obj

        if isinstance(obj, dict):
            return {k: self._walk_and_scan(v, detections) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._walk_and_scan(item, detections) for item in obj]

        # Numbers, bools, etc. — pass through
        return obj
