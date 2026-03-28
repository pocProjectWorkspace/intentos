"""InferenceRouter — routes LLM inference between local (Ollama) and cloud APIs.

Phase 2C.1: Privacy-aware routing based on complexity scoring and user consent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PrivacyMode(str, Enum):
    LOCAL_ONLY = "local_only"
    SMART_ROUTING = "smart_routing"
    PERFORMANCE = "performance"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class InferenceResult:
    text: str
    model: str
    backend: str  # "local" or "cloud"
    input_tokens: int
    output_tokens: int
    latency_ms: int
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InferenceError(Exception):
    """Raised when inference routing encounters an unrecoverable error."""


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class InferenceBackend(Protocol):
    def generate(self, prompt: str, model: str | None = None) -> InferenceResult: ...


# ---------------------------------------------------------------------------
# Complexity scoring constants
# ---------------------------------------------------------------------------

SIMPLE_TYPES = {"list", "read", "rename", "move", "copy", "delete", "date", "metadata"}
COMPLEX_TYPES = {"summarize", "research", "analyze", "compose", "extract", "plan", "organize"}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class InferenceRouter:
    """Routes inference requests between local and cloud backends."""

    def __init__(
        self,
        mode: PrivacyMode = PrivacyMode.SMART_ROUTING,
        local_threshold: float = 0.4,
    ) -> None:
        self._mode = mode
        self._local_threshold = local_threshold
        self._local_backend: Optional[InferenceBackend] = None
        self._cloud_backend: Optional[InferenceBackend] = None
        self._local_model: str = "phi3:mini"
        self._cloud_model: str = "claude-sonnet-4-20250514"
        self._consent_callback: Optional[Callable] = None

    # -- configuration ------------------------------------------------------

    def set_local_backend(self, backend: InferenceBackend) -> None:
        self._local_backend = backend

    def set_cloud_backend(self, backend: InferenceBackend) -> None:
        self._cloud_backend = backend

    def set_local_model(self, model: str) -> None:
        self._local_model = model

    def set_cloud_model(self, model: str) -> None:
        self._cloud_model = model

    def set_consent_callback(self, callback: Callable) -> None:
        self._consent_callback = callback

    # -- complexity scoring -------------------------------------------------

    def score_task(self, prompt: str, task_type: Optional[str]) -> float:
        """Return a complexity score in [0.0, 1.0]."""
        if task_type is None:
            task_type = "general"

        # Type component
        if task_type in SIMPLE_TYPES:
            type_score = 0.1
        elif task_type in COMPLEX_TYPES:
            type_score = 0.7
        else:
            type_score = 0.4  # general / unknown

        # Length component — normalised with a soft cap around 500 chars
        length = len(prompt)
        length_score = min(length / 500.0, 1.0)

        # Weighted blend
        score = 0.6 * type_score + 0.4 * length_score
        return max(0.0, min(1.0, score))

    # -- routing ------------------------------------------------------------

    def route(self, prompt: str, task_type: str = "general") -> InferenceResult:
        """Route an inference request and return the result."""

        # Edge case: empty prompt always goes local
        if not prompt:
            return self._run_local(prompt)

        if self._mode == PrivacyMode.LOCAL_ONLY:
            return self._route_local(prompt)

        if self._mode == PrivacyMode.PERFORMANCE:
            return self._route_cloud(prompt)

        # SMART_ROUTING
        return self._route_smart(prompt, task_type)

    # -- private routing strategies -----------------------------------------

    def _route_local(self, prompt: str) -> InferenceResult:
        if self._local_backend is None:
            raise InferenceError("No local backend configured for LOCAL_ONLY mode")
        return self._run_local(prompt)

    def _route_cloud(self, prompt: str) -> InferenceResult:
        if self._cloud_backend is None:
            raise InferenceError("No cloud backend configured for PERFORMANCE mode")
        try:
            return self._run_cloud(prompt)
        except Exception:
            return self._error_result("Cloud backend failed")

    def _route_smart(self, prompt: str, task_type: str) -> InferenceResult:
        score = self.score_task(prompt, task_type)

        if score < self._local_threshold:
            # Simple — try local first
            return self._try_local_with_cloud_fallback(prompt, task_type)
        else:
            # Complex — try cloud (with consent), fall back to local
            return self._try_cloud_with_local_fallback(prompt, task_type)

    def _try_local_with_cloud_fallback(self, prompt: str, task_type: str) -> InferenceResult:
        """Try local backend; on failure fall back to cloud if consent given."""
        if self._local_backend is not None:
            try:
                return self._run_local(prompt)
            except Exception:
                pass  # fall through to cloud fallback

        # Local failed or missing — attempt cloud fallback
        if self._cloud_backend is not None and self._get_consent(prompt, task_type):
            try:
                return self._run_cloud(prompt)
            except Exception:
                pass

        # Everything failed
        return self._error_result("All backends failed or unavailable")

    def _try_cloud_with_local_fallback(self, prompt: str, task_type: str) -> InferenceResult:
        """Try cloud (with consent); fall back to local on denial/failure."""
        if self._cloud_backend is not None and self._get_consent(prompt, task_type):
            try:
                return self._run_cloud(prompt)
            except Exception:
                pass  # fall through to local

        # Cloud unavailable/denied/failed — use local
        if self._local_backend is not None:
            try:
                return self._run_local(prompt)
            except Exception:
                pass

        return self._error_result("All backends failed or unavailable")

    # -- backend execution --------------------------------------------------

    def _run_local(self, prompt: str) -> InferenceResult:
        if self._local_backend is None:
            raise InferenceError("No local backend configured")
        return self._local_backend.generate(prompt, model=self._local_model)

    def _run_cloud(self, prompt: str) -> InferenceResult:
        if self._cloud_backend is None:
            raise InferenceError("No cloud backend configured")
        return self._cloud_backend.generate(prompt, model=self._cloud_model)

    # -- consent ------------------------------------------------------------

    def _get_consent(self, prompt: str, task_type: str) -> bool:
        """Return True if the user consents to cloud routing."""
        if self._consent_callback is None:
            return False  # safe default
        summary = prompt[:100]
        estimated_tokens = len(prompt) // 4  # rough estimate
        return self._consent_callback(summary, estimated_tokens, task_type)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _error_result(message: str) -> InferenceResult:
        return InferenceResult(
            text="",
            model="",
            backend="",
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            error=message,
        )
