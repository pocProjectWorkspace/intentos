"""
IntentOS Security Pipeline.

Single integration point that wires all security modules (sanitizer,
leak detector, sandbox) into agent execution. Provides process_input,
process_output, secure_execute, and check_paths with configurable
strict/non-strict modes and statistics tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.security.leak_detector import Action as LeakAction, LeakDetector, Severity
from core.security.sanitizer import ContentSanitizer
from core.security.sandbox import FileOp, Sandbox


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class InputResult:
    """Result of processing user input through the security pipeline."""
    sanitized_input: str
    has_warnings: bool
    warnings: List[str]
    blocked: bool


@dataclass
class OutputResult:
    """Result of processing agent output through the security pipeline."""
    sanitized_output: Dict[str, Any]
    had_leaks: bool
    leak_count: int
    action_taken: str  # "none" | "redacted" | "blocked"


@dataclass
class SecureExecutionResult:
    """Result of a secure agent execution."""
    output: Dict[str, Any]
    security_actions: List[str]
    blocked: bool
    error: Optional[str]


# ---------------------------------------------------------------------------
# SecurityPipeline
# ---------------------------------------------------------------------------

class SecurityPipeline:
    """
    Orchestrates sanitizer, leak detector, and sandbox checks around
    agent execution.

    Args:
        strict_mode: If True, block on any detection. If False, only
                     block on Critical severity.
        enabled: If False, bypass all security checks (dev/testing).
    """

    def __init__(self, strict_mode: bool = True, enabled: bool = True):
        self._strict_mode = strict_mode
        self._enabled = enabled
        self._sanitizer = ContentSanitizer()
        self._leak_detector = LeakDetector()

        # Statistics counters
        self._stats = {
            "total_scans": 0,
            "inputs_blocked": 0,
            "outputs_blocked": 0,
            "leaks_redacted": 0,
            "policy_violations": 0,
        }

    # -- Public API ---------------------------------------------------------

    def process_input(self, user_input: str) -> InputResult:
        """Scan user input for secrets and injection patterns."""
        self._stats["total_scans"] += 1

        if not self._enabled:
            return InputResult(
                sanitized_input=user_input,
                has_warnings=False,
                warnings=[],
                blocked=False,
            )

        # Run sanitizer input scan (detects injections, keys via policy rules)
        scan_result = self._sanitizer.scan_input(user_input)

        # Run leak detector to find credential patterns
        leak_detections = self._leak_detector.scan(user_input)

        warnings: List[str] = []
        blocked = False
        sanitized = user_input

        # Process sanitizer detections
        if scan_result.has_secrets:
            warnings.extend(scan_result.detections)
            # Check if any matched rule is a block-level (Critical severity)
            # The scan_input method only returns Critical/High rules
            # Shell injection and system file access are Critical -> block
            for detection_msg in scan_result.detections:
                if "shell_injection" in detection_msg or "system_file_access" in detection_msg:
                    blocked = True
                if "crypto_private_key" in detection_msg:
                    blocked = True

        # Process leak detections
        if leak_detections:
            for det in leak_detections:
                warnings.append(
                    f"[{det.pattern_name}] Credential detected (severity: {det.severity.value})"
                )
                if det.action == LeakAction.BLOCK or det.severity == Severity.CRITICAL:
                    blocked = True
            # Redact secrets from the sanitized input
            sanitized = self._leak_detector.redact(user_input)

        if blocked:
            self._stats["inputs_blocked"] += 1
            self._stats["policy_violations"] += 1

        has_warnings = len(warnings) > 0

        return InputResult(
            sanitized_input=sanitized,
            has_warnings=has_warnings,
            warnings=warnings,
            blocked=blocked,
        )

    def process_output(self, agent_output: Dict[str, Any]) -> OutputResult:
        """Scan agent output for leaked credentials and policy violations."""
        self._stats["total_scans"] += 1

        if not self._enabled:
            return OutputResult(
                sanitized_output=agent_output,
                had_leaks=False,
                leak_count=0,
                action_taken="none",
            )

        # Run leak detector on the full output dict
        scan_result = self._leak_detector.scan_agent_output(agent_output)

        if not scan_result.detections:
            return OutputResult(
                sanitized_output=agent_output,
                had_leaks=False,
                leak_count=0,
                action_taken="none",
            )

        # Determine highest severity action
        has_critical = any(
            d.severity == Severity.CRITICAL for d in scan_result.detections
        )
        has_high = any(
            d.severity == Severity.HIGH for d in scan_result.detections
        )

        leak_count = len(scan_result.detections)

        # Decide action based on mode
        if has_critical or (self._strict_mode and (has_high or leak_count > 0)):
            action = "blocked"
            self._stats["outputs_blocked"] += 1
            self._stats["policy_violations"] += 1
            return OutputResult(
                sanitized_output={"error": "Output blocked due to detected credential leak"},
                had_leaks=True,
                leak_count=leak_count,
                action_taken=action,
            )

        # Non-strict with High or lower: redact
        self._stats["leaks_redacted"] += leak_count
        return OutputResult(
            sanitized_output=scan_result.sanitized,
            had_leaks=True,
            leak_count=leak_count,
            action_taken="redacted",
        )

    def secure_execute(
        self,
        handler: Callable,
        input_dict: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        sandbox: Optional[Sandbox] = None,
    ) -> SecureExecutionResult:
        """
        Wrap an agent call with full security: scan input, check sandbox,
        execute, scan output.
        """
        security_actions: List[str] = []

        # 1. Scan all string values in input_dict for secrets
        for key, value in input_dict.items():
            if isinstance(value, str) and key != "paths":
                input_result = self.process_input(value)
                if input_result.blocked:
                    return SecureExecutionResult(
                        output={},
                        security_actions=["input_blocked"],
                        blocked=True,
                        error=f"Input blocked: security issue detected in '{key}'",
                    )
                if input_result.has_warnings:
                    security_actions.append(f"input_warning:{key}")
                    # Replace the value with sanitized version
                    input_dict = dict(input_dict)
                    input_dict[key] = input_result.sanitized_input

        # 2. Check sandbox permissions for file paths
        if sandbox is not None:
            paths = input_dict.get("paths", [])
            if isinstance(paths, list) and paths:
                # Determine operation from context or default to WRITE
                operation = FileOp.WRITE
                denied = self.check_paths(paths, sandbox, operation)
                if denied:
                    denied_summary = "; ".join(
                        f"{p}: {reason}" for p, reason in denied
                    )
                    return SecureExecutionResult(
                        output={},
                        security_actions=["sandbox_denied"],
                        blocked=True,
                        error=f"Sandbox denied paths: {denied_summary}",
                    )

        # 3. Execute the agent handler
        try:
            raw_output = handler(input_dict, context)
        except Exception as exc:
            return SecureExecutionResult(
                output={},
                security_actions=security_actions,
                blocked=True,
                error=f"Agent execution failed: {exc}",
            )

        # 4. Scan output for leaks
        output_result = self.process_output(raw_output)

        if output_result.action_taken == "blocked":
            security_actions.append("output_blocked")
            return SecureExecutionResult(
                output={},
                security_actions=security_actions,
                blocked=True,
                error="Output blocked: critical credential leak detected",
            )

        if output_result.action_taken == "redacted":
            security_actions.append("output_redacted")

        return SecureExecutionResult(
            output=output_result.sanitized_output,
            security_actions=security_actions,
            blocked=False,
            error=None,
        )

    def check_paths(
        self,
        paths: List[str],
        sandbox: Sandbox,
        operation: FileOp,
    ) -> List[Tuple[str, str]]:
        """
        Check all paths against sandbox policy.

        Returns list of (path, reason) tuples for denied paths.
        """
        if not paths:
            return []

        denied: List[Tuple[str, str]] = []
        for path in paths:
            result = sandbox.check(operation, path)
            if not result.allowed:
                denied.append((path, result.reason))

        return denied

    def get_stats(self) -> Dict[str, int]:
        """Return pipeline statistics."""
        return dict(self._stats)
