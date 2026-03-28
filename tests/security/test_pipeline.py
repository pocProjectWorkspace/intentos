"""
Tests for the IntentOS Security Pipeline.

Covers: InputResult, OutputResult, SecureExecutionResult,
process_input, process_output, secure_execute, check_paths,
pipeline configuration, and statistics tracking.
"""

import pytest

from core.security.pipeline import (
    InputResult,
    OutputResult,
    SecureExecutionResult,
    SecurityPipeline,
)
from core.security.sandbox import FileOp, Sandbox, SandboxPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sandbox(policy=SandboxPolicy.WORKSPACE_WRITE, workspace="/tmp/ws"):
    """Create a simple sandbox for testing."""
    return Sandbox(
        policy=policy,
        granted_paths=["/tmp/ws"],
        workspace=workspace,
    )


def _echo_handler(input_dict, context=None):
    """Agent handler that echoes its input."""
    return {"result": input_dict.get("prompt", "")}


def _secret_handler(input_dict, context=None):
    """Agent handler that leaks a secret in its output."""
    return {"result": f"Here is the key: {input_dict.get('secret', '')}"}


# ---------------------------------------------------------------------------
# Input Processing (tests 1-5)
# ---------------------------------------------------------------------------

class TestProcessInput:

    def test_returns_input_result(self):
        """1. process_input returns an InputResult."""
        pipe = SecurityPipeline()
        result = pipe.process_input("hello world")
        assert isinstance(result, InputResult)

    def test_clean_input_passes_unchanged(self):
        """3. Clean input passes through unchanged."""
        pipe = SecurityPipeline()
        result = pipe.process_input("Tell me a joke")
        assert result.sanitized_input == "Tell me a joke"
        assert result.has_warnings is False
        assert result.warnings == []
        assert result.blocked is False

    def test_input_result_fields(self):
        """2. InputResult contains the expected fields."""
        pipe = SecurityPipeline()
        result = pipe.process_input("safe text")
        assert hasattr(result, "sanitized_input")
        assert hasattr(result, "has_warnings")
        assert hasattr(result, "warnings")
        assert hasattr(result, "blocked")

    def test_api_key_in_input_flagged(self):
        """4. Input with embedded API key triggers warning, key not sent to LLM."""
        pipe = SecurityPipeline()
        dangerous = "Use this key sk-ant-api03-AAAABBBBCCCCDDDDEEEE to call the API"
        result = pipe.process_input(dangerous)
        assert result.has_warnings is True
        assert len(result.warnings) > 0
        # The API key should not appear in sanitized_input
        assert "sk-ant-api03" not in result.sanitized_input

    def test_shell_injection_blocked(self):
        """5. Input with shell injection pattern is blocked."""
        pipe = SecurityPipeline()
        result = pipe.process_input("run this: ; rm -rf /")
        assert result.blocked is True


# ---------------------------------------------------------------------------
# Output Processing (tests 6-10)
# ---------------------------------------------------------------------------

class TestProcessOutput:

    def test_runs_leak_detector_and_sanitizer(self):
        """6. process_output runs leak detector + sanitizer on all string values."""
        pipe = SecurityPipeline()
        output = {"result": "clean text", "status": "ok"}
        result = pipe.process_output(output)
        assert isinstance(result, OutputResult)

    def test_api_key_in_output_redacted(self):
        """7. Output with API key in result is redacted before returning."""
        pipe = SecurityPipeline()
        output = {"result": "Key is ghp_aB3dE6fG7hI8jK0lM1nO2pQ3rS4tU5vW6xY7"}
        result = pipe.process_output(output)
        assert result.had_leaks is True
        assert result.leak_count >= 1
        assert "ghp_" not in result.sanitized_output.get("result", "")
        assert result.action_taken in ("redacted", "blocked")

    def test_pem_key_blocks_output(self):
        """8. Output with PEM key is blocked entirely."""
        pipe = SecurityPipeline()
        output = {"result": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."}
        result = pipe.process_output(output)
        assert result.action_taken == "blocked"

    def test_clean_output_passes(self):
        """9. Clean output passes through unchanged."""
        pipe = SecurityPipeline()
        output = {"result": "All good", "count": 42}
        result = pipe.process_output(output)
        assert result.sanitized_output == output
        assert result.had_leaks is False
        assert result.leak_count == 0
        assert result.action_taken == "none"

    def test_output_result_fields(self):
        """10. OutputResult has required fields."""
        pipe = SecurityPipeline()
        result = pipe.process_output({"x": "y"})
        assert hasattr(result, "sanitized_output")
        assert hasattr(result, "had_leaks")
        assert hasattr(result, "leak_count")
        assert hasattr(result, "action_taken")
        assert result.action_taken in ("none", "redacted", "blocked")


# ---------------------------------------------------------------------------
# Agent Execution Wrapping (tests 11-15)
# ---------------------------------------------------------------------------

class TestSecureExecute:

    def test_wraps_agent_call(self):
        """11. secure_execute wraps an agent call with full security."""
        pipe = SecurityPipeline()
        result = pipe.secure_execute(_echo_handler, {"prompt": "hello"}, context={})
        assert isinstance(result, SecureExecutionResult)
        assert result.output == {"result": "hello"}
        assert result.blocked is False
        assert result.error is None

    def test_blocked_input_prevents_execution(self):
        """12. If input has blocked content, agent never called."""
        pipe = SecurityPipeline()
        called = []

        def tracking_handler(input_dict, context=None):
            called.append(True)
            return {"result": "done"}

        result = pipe.secure_execute(
            tracking_handler,
            {"prompt": "run this: ; rm -rf /"},
            context={},
        )
        assert result.blocked is True
        assert result.error is not None
        assert len(called) == 0

    def test_critical_leak_blocks_output(self):
        """13. If output has Critical leak, result blocked."""
        pipe = SecurityPipeline()

        def pem_handler(input_dict, context=None):
            return {"result": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."}

        result = pipe.secure_execute(pem_handler, {"prompt": "get key"}, context={})
        assert result.blocked is True
        assert result.error is not None

    def test_high_leak_redacted_with_warning(self):
        """14. If output has High leak, secrets redacted, result returned with warning."""
        pipe = SecurityPipeline(strict_mode=False)

        def token_handler(input_dict, context=None):
            return {"result": "Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123.def456"}

        result = pipe.secure_execute(token_handler, {"prompt": "get token"}, context={})
        assert result.blocked is False
        assert "Bearer" not in result.output.get("result", "")
        assert len(result.security_actions) > 0

    def test_sandbox_failure_prevents_execution(self):
        """15. If sandbox check fails, agent never called."""
        pipe = SecurityPipeline()
        sandbox = _make_sandbox()
        called = []

        def tracking_handler(input_dict, context=None):
            called.append(True)
            return {"result": "done"}

        result = pipe.secure_execute(
            tracking_handler,
            {"prompt": "write file", "paths": ["/etc/passwd"]},
            context={},
            sandbox=sandbox,
        )
        assert result.blocked is True
        assert result.error is not None
        assert len(called) == 0


# ---------------------------------------------------------------------------
# Sandbox Integration (tests 16-18)
# ---------------------------------------------------------------------------

class TestCheckPaths:

    def test_denied_paths_returned(self):
        """16. check_paths returns denied paths with reasons."""
        pipe = SecurityPipeline()
        sandbox = _make_sandbox()
        denied = pipe.check_paths(
            ["/etc/passwd", "/tmp/ws/safe.txt"],
            sandbox,
            FileOp.WRITE,
        )
        # /etc/passwd should be denied (outside workspace for WRITE)
        assert len(denied) >= 1
        paths_denied = [d[0] for d in denied]
        assert any("/etc/passwd" in p for p in paths_denied)

    def test_all_paths_within_workspace_ok(self):
        """16b. All paths within workspace pass."""
        pipe = SecurityPipeline()
        sandbox = _make_sandbox()
        denied = pipe.check_paths(
            ["/tmp/ws/a.txt", "/tmp/ws/b.txt"],
            sandbox,
            FileOp.WRITE,
        )
        assert denied == []

    def test_empty_paths_passes(self):
        """18. Empty paths list passes."""
        pipe = SecurityPipeline()
        sandbox = _make_sandbox()
        denied = pipe.check_paths([], sandbox, FileOp.READ)
        assert denied == []


# ---------------------------------------------------------------------------
# Pipeline Configuration (tests 19-21)
# ---------------------------------------------------------------------------

class TestPipelineConfiguration:

    def test_strict_mode_blocks_on_any_detection(self):
        """19. strict_mode=True blocks on any detection."""
        pipe = SecurityPipeline(strict_mode=True)
        # A bearer token is High severity - strict mode should block it
        output = {"result": "Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123.def456"}
        result = pipe.process_output(output)
        assert result.action_taken == "blocked"

    def test_non_strict_only_blocks_critical(self):
        """20. strict_mode=False only blocks on Critical."""
        pipe = SecurityPipeline(strict_mode=False)
        # A bearer token is High severity - non-strict should redact, not block
        output = {"result": "Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123.def456"}
        result = pipe.process_output(output)
        assert result.action_taken == "redacted"

    def test_disabled_passes_everything(self):
        """21. enabled=False passes everything through."""
        pipe = SecurityPipeline(enabled=False)
        result_in = pipe.process_input("; rm -rf /")
        assert result_in.blocked is False
        assert result_in.sanitized_input == "; rm -rf /"

        output = {"result": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."}
        result_out = pipe.process_output(output)
        assert result_out.action_taken == "none"
        assert result_out.sanitized_output == output


# ---------------------------------------------------------------------------
# Statistics (test 22)
# ---------------------------------------------------------------------------

class TestStatistics:

    def test_get_stats_tracks_counters(self):
        """22. get_stats returns expected counters."""
        pipe = SecurityPipeline()

        # Generate some activity
        pipe.process_input("hello")
        pipe.process_input("; rm -rf /")
        pipe.process_output({"result": "clean"})
        pipe.process_output({"result": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."})
        pipe.process_output({"result": "Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123.def456"})

        stats = pipe.get_stats()
        assert stats["total_scans"] >= 5
        assert stats["inputs_blocked"] >= 1
        assert stats["outputs_blocked"] >= 1
        assert stats["leaks_redacted"] >= 0
        assert "policy_violations" in stats
