"""
Tests for the IntentOS Leak Detection Pipeline.

Covers: API key detection, private key detection, auth token detection,
high-entropy strings, severity levels, scan/redact/scan_agent_output,
false positive prevention, performance, and edge cases.
"""

import time

import pytest

from core.security.leak_detector import (
    Action,
    CredentialPattern,
    LeakDetection,
    LeakDetector,
    ScanResult,
    Severity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector():
    return LeakDetector()


# ---------------------------------------------------------------------------
# 1. API Key Detection
# ---------------------------------------------------------------------------

class TestAPIKeyDetection:
    """Detect common API key formats."""

    def test_anthropic_key(self, detector):
        text = "key = sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("anthropic" in n.lower() for n in names)

    def test_openai_key_sk_proj(self, detector):
        text = "OPENAI_API_KEY=sk-proj-abcdefghij1234567890abcdefghij1234567890abcdef"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("openai" in n.lower() for n in names)

    def test_openai_key_sk_long(self, detector):
        text = "sk-" + "a" * 40
        results = detector.scan(text)
        assert len(results) >= 1

    def test_aws_access_key(self, detector):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("aws" in n.lower() for n in names)

    def test_github_pat(self, detector):
        token = "ghp_" + "a" * 36
        results = detector.scan(f"token: {token}")
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("github" in n.lower() for n in names)

    def test_github_oauth(self, detector):
        token = "gho_" + "B" * 36
        results = detector.scan(f"oauth: {token}")
        assert len(results) >= 1

    def test_github_app(self, detector):
        token = "ghs_" + "C" * 36
        results = detector.scan(f"app: {token}")
        assert len(results) >= 1

    def test_google_api_key(self, detector):
        text = "AIzaSyC_abcdefg1234567890-ABCDE_fghijkl"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("google" in n.lower() for n in names)

    def test_slack_token(self, detector):
        text = "SLACK_TOKEN=xoxb-1234567890-abcdefghij"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("slack" in n.lower() for n in names)

    def test_sendgrid_key(self, detector):
        text = "SG." + "a" * 22 + "." + "b" * 43
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("sendgrid" in n.lower() for n in names)


# ---------------------------------------------------------------------------
# 2. Private Key Detection
# ---------------------------------------------------------------------------

class TestPrivateKeyDetection:
    """Detect PEM and SSH private keys."""

    def test_rsa_private_key(self, detector):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        results = detector.scan(text)
        assert len(results) >= 1
        assert any("private_key" in r.pattern_name.lower() or "private key" in r.pattern_name.lower() for r in results)

    def test_ec_private_key(self, detector):
        text = "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEE..."
        results = detector.scan(text)
        assert len(results) >= 1

    def test_openssh_private_key(self, detector):
        text = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC..."
        results = detector.scan(text)
        assert len(results) >= 1
        assert any("openssh" in r.pattern_name.lower() for r in results)

    def test_generic_private_key(self, detector):
        text = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBg..."
        results = detector.scan(text)
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# 3. Auth Token Detection
# ---------------------------------------------------------------------------

class TestAuthTokenDetection:
    """Detect Bearer, Basic, and AWS Signature auth."""

    def test_bearer_token(self, detector):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("bearer" in n.lower() for n in names)

    def test_basic_auth(self, detector):
        text = "Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQxMjM0NTY="
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("basic" in n.lower() for n in names)

    def test_aws_signature(self, detector):
        text = "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20230101/us-east-1/s3/aws4_request"
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("aws" in n.lower() for n in names)


# ---------------------------------------------------------------------------
# 4. High-Entropy String Detection
# ---------------------------------------------------------------------------

class TestHighEntropyDetection:
    """Detect long hex strings that look like secrets."""

    def test_hex_string_40_chars(self, detector):
        text = "secret=" + "a1b2c3d4e5" * 4  # 40 hex chars
        results = detector.scan(text)
        assert len(results) >= 1
        names = [r.pattern_name for r in results]
        assert any("hex" in n.lower() or "entropy" in n.lower() for n in names)

    def test_hex_string_64_chars(self, detector):
        text = "hash=" + "deadbeef" * 8  # 64 hex chars
        results = detector.scan(text)
        assert len(results) >= 1

    def test_short_hex_not_flagged(self, detector):
        """Hex strings under 40 chars should not trigger."""
        text = "commit=abcdef1234567890"  # 16 chars
        results = detector.scan(text)
        hex_results = [r for r in results if "hex" in r.pattern_name.lower() or "entropy" in r.pattern_name.lower()]
        assert len(hex_results) == 0


# ---------------------------------------------------------------------------
# 5. Severity Levels
# ---------------------------------------------------------------------------

class TestSeverityLevels:
    """Verify correct severity and action assignment."""

    def test_critical_block_for_anthropic(self, detector):
        text = "sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        results = detector.scan(text)
        critical = [r for r in results if r.severity == Severity.CRITICAL]
        assert len(critical) >= 1
        assert all(r.action == Action.BLOCK for r in critical)

    def test_critical_block_for_aws(self, detector):
        text = "AKIAIOSFODNN7EXAMPLE"
        results = detector.scan(text)
        critical = [r for r in results if r.severity == Severity.CRITICAL]
        assert len(critical) >= 1

    def test_high_redact_for_bearer(self, detector):
        text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0"
        results = detector.scan(text)
        high = [r for r in results if r.severity == Severity.HIGH]
        assert len(high) >= 1
        assert all(r.action == Action.REDACT for r in high)

    def test_medium_warn_for_hex(self, detector):
        text = "a1b2c3d4e5" * 4  # 40 hex chars
        results = detector.scan(text)
        medium = [r for r in results if r.severity == Severity.MEDIUM]
        assert len(medium) >= 1
        assert all(r.action == Action.WARN for r in medium)

    def test_critical_block_for_private_key(self, detector):
        text = "-----BEGIN RSA PRIVATE KEY-----"
        results = detector.scan(text)
        critical = [r for r in results if r.severity == Severity.CRITICAL]
        assert len(critical) >= 1
        assert all(r.action == Action.BLOCK for r in critical)


# ---------------------------------------------------------------------------
# 6. scan() Method
# ---------------------------------------------------------------------------

class TestScanMethod:
    """Verify scan() returns correct LeakDetection objects."""

    def test_returns_list(self, detector):
        results = detector.scan("nothing secret here")
        assert isinstance(results, list)

    def test_leak_detection_fields(self, detector):
        text = "key=sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        results = detector.scan(text)
        assert len(results) >= 1
        d = results[0]
        assert isinstance(d, LeakDetection)
        assert d.pattern_name
        assert d.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
        assert d.action in (Action.BLOCK, Action.REDACT, Action.WARN)
        assert isinstance(d.matched_text, str)
        assert len(d.matched_text) <= 14  # 10 chars + "..."
        assert d.start_pos >= 0
        assert d.end_pos > d.start_pos

    def test_position_accuracy(self, detector):
        prefix = "prefix: "
        secret = "AKIAIOSFODNN7EXAMPLE"
        text = prefix + secret
        results = detector.scan(text)
        aws = [r for r in results if "aws" in r.pattern_name.lower()]
        assert len(aws) >= 1
        assert aws[0].start_pos == len(prefix)

    def test_multiple_detections(self, detector):
        text = "key1=AKIAIOSFODNN7EXAMPLE key2=ghp_" + "a" * 36
        results = detector.scan(text)
        assert len(results) >= 2

    def test_clean_text_returns_empty(self, detector):
        results = detector.scan("This is a perfectly normal sentence about programming.")
        assert results == []


# ---------------------------------------------------------------------------
# 7. scan_agent_output() Method
# ---------------------------------------------------------------------------

class TestScanAgentOutput:
    """scan_agent_output() recursively scans all strings in nested dicts."""

    def test_flat_dict(self, detector):
        output = {"response": "Your key is sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"}
        result = detector.scan_agent_output(output)
        assert isinstance(result, ScanResult)
        assert len(result.detections) >= 1

    def test_nested_dict(self, detector):
        output = {
            "data": {
                "inner": {
                    "secret": "AKIAIOSFODNN7EXAMPLE"
                }
            }
        }
        result = detector.scan_agent_output(output)
        assert len(result.detections) >= 1

    def test_list_values(self, detector):
        output = {
            "messages": [
                "hello",
                "your token is ghp_" + "a" * 36,
            ]
        }
        result = detector.scan_agent_output(output)
        assert len(result.detections) >= 1

    def test_none_values(self, detector):
        output = {"key": None, "other": "safe text"}
        result = detector.scan_agent_output(output)
        assert len(result.detections) == 0

    def test_sanitized_copy(self, detector):
        secret = "sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        output = {"response": f"Your key is {secret}"}
        result = detector.scan_agent_output(output)
        # The sanitized copy should not contain the secret
        assert secret not in result.sanitized["response"]
        assert "[REDACTED" in result.sanitized["response"]

    def test_mixed_nested_structure(self, detector):
        output = {
            "level1": {
                "level2": [
                    {"secret": "Bearer " + "x" * 30},
                    None,
                    "safe",
                ]
            },
            "clean": "no secrets",
        }
        result = detector.scan_agent_output(output)
        assert len(result.detections) >= 1


# ---------------------------------------------------------------------------
# 8. redact() Method
# ---------------------------------------------------------------------------

class TestRedactMethod:
    """redact() replaces secrets with [REDACTED:{pattern_name}]."""

    def test_redact_single(self, detector):
        text = "key=AKIAIOSFODNN7EXAMPLE"
        redacted = detector.redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert "[REDACTED:" in redacted

    def test_redact_multiple(self, detector):
        text = "aws=AKIAIOSFODNN7EXAMPLE github=ghp_" + "a" * 36
        redacted = detector.redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert "ghp_" not in redacted
        assert redacted.count("[REDACTED:") >= 2

    def test_redact_preserves_clean_text(self, detector):
        text = "Hello AKIAIOSFODNN7EXAMPLE World"
        redacted = detector.redact(text)
        assert "Hello" in redacted
        assert "World" in redacted

    def test_redact_clean_text_unchanged(self, detector):
        text = "Nothing secret here"
        assert detector.redact(text) == text


# ---------------------------------------------------------------------------
# 9. False Positive Prevention
# ---------------------------------------------------------------------------

class TestFalsePositivePrevention:
    """Common words should NOT trigger detection."""

    def test_tokenize_not_flagged(self, detector):
        results = detector.scan("We need to tokenize the input text for the model.")
        token_results = [r for r in results if "bearer" in r.pattern_name.lower() or "basic" in r.pattern_name.lower()]
        assert len(token_results) == 0

    def test_token_count_not_flagged(self, detector):
        results = detector.scan("The token_count is 4096 for this request.")
        token_results = [r for r in results if "bearer" in r.pattern_name.lower() or "basic" in r.pattern_name.lower()]
        assert len(token_results) == 0

    def test_author_key_not_flagged(self, detector):
        results = detector.scan("The author_key field identifies the document owner.")
        # Should not flag as API key
        assert len(results) == 0

    def test_sketch_prefix_not_openai(self, detector):
        """'sk-' inside a normal word should not trigger."""
        results = detector.scan("The risk-assessment was completed.")
        openai = [r for r in results if "openai" in r.pattern_name.lower()]
        assert len(openai) == 0

    def test_public_key_not_flagged(self, detector):
        """Public keys should NOT be flagged."""
        text = "-----BEGIN PUBLIC KEY-----"
        results = detector.scan(text)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# 10. Performance
# ---------------------------------------------------------------------------

class TestPerformance:
    """Scanning should be fast, no ReDoS vulnerabilities."""

    def test_100kb_text_completes(self, detector):
        text = "The quick brown fox jumps. " * 4000  # ~108KB
        start = time.time()
        detector.scan(text)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Scan took {elapsed:.2f}s, expected < 5s"

    def test_100kb_with_some_secrets(self, detector):
        chunks = ["Normal text. "] * 3000
        chunks[500] = "key=AKIAIOSFODNN7EXAMPLE "
        chunks[1500] = "ghp_" + "a" * 36 + " "
        text = "".join(chunks)
        start = time.time()
        results = detector.scan(text)
        elapsed = time.time() - start
        assert elapsed < 5.0
        assert len(results) >= 2


# ---------------------------------------------------------------------------
# 11. Empty / None Input
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Handle empty and None input gracefully."""

    def test_empty_string(self, detector):
        results = detector.scan("")
        assert results == []

    def test_none_input(self, detector):
        results = detector.scan(None)
        assert results == []

    def test_redact_empty(self, detector):
        assert detector.redact("") == ""

    def test_redact_none(self, detector):
        assert detector.redact(None) == ""

    def test_scan_agent_output_empty_dict(self, detector):
        result = detector.scan_agent_output({})
        assert result.detections == []
        assert result.sanitized == {}
