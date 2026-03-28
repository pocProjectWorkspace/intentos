"""SOP (Standard Operating Procedure) Engine — Phase 2B.3.

Enforces structured task execution through seven ordered phases,
inspired by MetaGPT's SOP-driven workflows.
"""

from __future__ import annotations

import enum
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Phase(enum.IntEnum):
    PARSE = 1
    PLAN = 2
    VALIDATE = 3
    PREVIEW = 4
    EXECUTE = 5
    VERIFY = 6
    REPORT = 7


class RecoveryAction(enum.Enum):
    RETRY = "retry"
    REPLAN = "replan"
    ABORT = "abort"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class PhaseResult(BaseModel):
    phase: Phase
    status: str  # "success" | "error" | "skipped"
    output: Any = None
    duration_ms: int = 0
    error_message: Optional[str] = None

    model_config = ConfigDict(use_enum_values=False)


class SOPResult(BaseModel):
    phases: List[PhaseResult] = []
    overall_status: str = "success"
    total_duration_ms: int = 0

    model_config = ConfigDict(use_enum_values=False)

    def get_phase(self, phase: Phase) -> Optional[PhaseResult]:
        for pr in self.phases:
            if pr.phase is phase:
                return pr
        return None

    @property
    def succeeded(self) -> bool:
        return self.overall_status == "success"


# ---------------------------------------------------------------------------
# SOPExecutor
# ---------------------------------------------------------------------------

class SOPExecutor:
    """Runs tasks through the seven SOP phases in strict order."""

    def __init__(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.context: Dict[str, Any] = context if context is not None else {}
        self._handlers: Dict[Phase, Callable] = {}
        self._error_handler: Optional[Callable[[PhaseResult], RecoveryAction]] = None
        self._current_phase: Phase = Phase.PARSE
        self._is_complete: bool = False

        # Event hooks
        self.on_phase_start: Optional[Callable[[Phase, Any], None]] = None
        self.on_phase_complete: Optional[Callable[[PhaseResult], None]] = None

    # -- properties ---------------------------------------------------------

    @property
    def current_phase(self) -> Phase:
        return self._current_phase

    @property
    def is_complete(self) -> bool:
        return self._is_complete

    # -- registration -------------------------------------------------------

    def register_handler(self, phase: Phase, handler: Callable) -> None:
        self._handlers[phase] = handler

    def register_error_handler(self, callback: Callable[[PhaseResult], RecoveryAction]) -> None:
        self._error_handler = callback

    # -- static helpers -----------------------------------------------------

    @staticmethod
    def needs_preview(subtasks: List[Dict[str, Any]]) -> bool:
        """Return True if any subtask is destructive or batch size > 5."""
        if len(subtasks) > 5:
            return True
        destructive = {"delete", "move"}
        return any(st.get("action") in destructive for st in subtasks)

    # -- execution ----------------------------------------------------------

    def run(self, initial_input: Any, skip_preview: bool = False) -> SOPResult:
        all_phases = list(Phase)
        results: List[PhaseResult] = []
        phase_input = initial_input
        overall_start = time.monotonic()
        idx = 0

        while idx < len(all_phases):
            phase = all_phases[idx]
            self._current_phase = phase

            # Determine if this phase should be skipped
            should_skip = False
            if phase is Phase.PREVIEW and skip_preview:
                should_skip = True
            if phase not in self._handlers:
                should_skip = True

            if should_skip:
                pr = PhaseResult(phase=phase, status="skipped", output=None, duration_ms=0)
                results.append(pr)
                if self.on_phase_start:
                    self.on_phase_start(phase, phase_input)
                if self.on_phase_complete:
                    self.on_phase_complete(pr)
                # Skipped phases pass through the previous input unchanged.
                idx += 1
                continue

            # Fire on_phase_start hook
            if self.on_phase_start:
                self.on_phase_start(phase, phase_input)

            # Execute handler
            pr = self._execute_phase(phase, phase_input)

            if pr.status == "success":
                results.append(pr)
                if self.on_phase_complete:
                    self.on_phase_complete(pr)
                phase_input = pr.output
                idx += 1
            else:
                # Error path
                if self.on_phase_complete:
                    self.on_phase_complete(pr)

                recovery = RecoveryAction.ABORT
                if self._error_handler:
                    recovery = self._error_handler(pr)

                if recovery is RecoveryAction.RETRY:
                    # Re-run the same phase; do NOT append the failed result,
                    # the retry will produce a new one.
                    continue
                elif recovery is RecoveryAction.REPLAN:
                    # Go back to PLAN phase.  Reset results back to just PARSE
                    # and re-run from PLAN.
                    plan_idx = all_phases.index(Phase.PLAN)
                    # Keep results up to (but not including) PLAN.
                    results = [r for r in results if r.phase.value < Phase.PLAN.value]
                    # Feed the PARSE output as input to PLAN.
                    parse_pr = next((r for r in results if r.phase is Phase.PARSE), None)
                    phase_input = parse_pr.output if parse_pr else initial_input
                    idx = plan_idx
                    continue
                else:
                    # ABORT
                    results.append(pr)
                    total_ms = int((time.monotonic() - overall_start) * 1000)
                    return SOPResult(
                        phases=results,
                        overall_status="error",
                        total_duration_ms=total_ms,
                    )

        total_ms = int((time.monotonic() - overall_start) * 1000)
        # Check if all non-skipped phases succeeded
        has_error = any(pr.status == "error" for pr in results)
        overall = "error" if has_error else "success"

        if overall == "success" and any(pr.phase is Phase.REPORT for pr in results):
            self._is_complete = True

        return SOPResult(
            phases=results,
            overall_status=overall,
            total_duration_ms=total_ms,
        )

    def _execute_phase(self, phase: Phase, phase_input: Any) -> PhaseResult:
        handler = self._handlers[phase]
        start = time.monotonic()
        try:
            output = handler(phase_input, self.context)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return PhaseResult(
                phase=phase,
                status="success",
                output=output,
                duration_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return PhaseResult(
                phase=phase,
                status="error",
                output=None,
                duration_ms=elapsed_ms,
                error_message=str(exc),
            )
