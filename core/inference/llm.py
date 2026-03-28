"""LLMService — unified inference integration layer for IntentOS.

Wires InferenceRouter and CostManager into a single interface
the kernel calls for all LLM operations.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.inference.hardware import HardwareDetector, HardwareProfile, ModelRecommendation
from core.inference.providers import (
    AnthropicBackend,
    OllamaBackend,
    OpenAIBackend,
    GeminiBackend,
    CustomBackend,
    LLMProvider,
    ProviderConfig,
    DEFAULT_MODELS,
    create_backend,
)
from core.inference.router import (
    InferenceBackend,
    InferenceResult,
    InferenceRouter,
    PrivacyMode,
)
from core.orchestration.cost_manager import BudgetExceededException, CostManager


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Unified response from any LLM call."""

    text: str
    model: str
    backend: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


# ---------------------------------------------------------------------------
# Provider config helper
# ---------------------------------------------------------------------------

def get_provider_config(credential_provider: Any) -> Optional[ProviderConfig]:
    """Build a ProviderConfig from the credential provider.

    Reads LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL from the
    credential store or environment.  Returns None when no provider is
    configured.
    """
    provider_str = credential_provider.get("LLM_PROVIDER")
    if not provider_str:
        return None

    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        return None

    api_key = credential_provider.get("LLM_API_KEY") or ""
    model = credential_provider.get("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")
    base_url = credential_provider.get("LLM_BASE_URL")

    return ProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


# ---------------------------------------------------------------------------
# LLMService
# ---------------------------------------------------------------------------

# Approximate max context window in tokens for truncation logic
_DEFAULT_MAX_CONTEXT_TOKENS = 4096


class LLMService:
    """Unified inference interface for the IntentOS kernel.

    Wraps InferenceRouter + CostManager, provides convenience methods
    for intent parsing, summarisation, and context assembly.
    """

    def __init__(
        self,
        privacy_mode: PrivacyMode = PrivacyMode.SMART_ROUTING,
        credential_provider: Any = None,
        budget: Optional[float] = None,
    ) -> None:
        # Hardware detection
        self._hw_detector = HardwareDetector()
        self._hw_profile: HardwareProfile = self._hw_detector.detect()
        self._model_rec: ModelRecommendation = self._hw_detector.recommend_model(self._hw_profile)

        # Router
        self._router = InferenceRouter(mode=privacy_mode)
        self._router.set_local_model(self._model_rec.model_name)

        # Cost tracking
        strict = budget is not None
        self._cost_manager = CostManager(budget=budget, strict=strict)

        # Statistics
        self._calls_local = 0
        self._calls_cloud = 0
        self._total_latency_ms: float = 0.0

        # Store privacy mode for config
        self._privacy_mode = privacy_mode

        # Auto-setup backends
        self._setup_backends(credential_provider)

    def _setup_backends(self, credential_provider: Any = None) -> None:
        """Auto-detect and configure inference backends.

        Supports multiple cloud providers via ProviderConfig.  Falls back to
        legacy ANTHROPIC_API_KEY when no explicit provider config is found.
        """
        cloud_backend = None

        # Try to read provider config from credential provider
        try:
            if credential_provider:
                config = get_provider_config(credential_provider)
                if config and config.provider != LLMProvider.OLLAMA:
                    cloud_backend = create_backend(config)
                elif config and config.provider == LLMProvider.OLLAMA:
                    # Provider is local-only; skip cloud, set up Ollama below
                    pass
        except Exception:
            pass

        # Legacy fallback: if no cloud backend yet, try ANTHROPIC_API_KEY
        if cloud_backend is None:
            try:
                if credential_provider:
                    api_key = credential_provider.get("ANTHROPIC_API_KEY")
                else:
                    import os
                    api_key = os.environ.get("ANTHROPIC_API_KEY")

                if api_key:
                    cloud_backend = AnthropicBackend(api_key=api_key)
            except Exception:
                pass

        if cloud_backend is not None:
            self._router.set_cloud_backend(cloud_backend)

        # Local backend (Ollama — only if running)
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            local = OllamaBackend(default_model=self._model_rec.model_name)
            self._router.set_local_backend(local)
        except Exception:
            pass  # Ollama not running

    # -- Hardware info ------------------------------------------------------

    def get_hardware_profile(self) -> HardwareProfile:
        return self._hw_profile

    def get_recommended_model(self) -> ModelRecommendation:
        return self._model_rec

    # -- Core inference -----------------------------------------------------

    def generate(self, prompt: str, task_type: str = "general") -> LLMResponse:
        """Route a prompt through InferenceRouter, record cost, return LLMResponse."""
        result: InferenceResult = self._router.route(prompt, task_type=task_type)

        # Calculate cost
        cost = self._cost_manager.estimate_cost(
            result.model or "unknown",
            result.input_tokens,
            result.output_tokens,
        )

        # Record in cost manager (may raise BudgetExceededException)
        self._cost_manager.record_usage(
            model=result.model or "unknown",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=cost,
            task_id=task_type,
        )

        # Update stats
        if result.backend == "local":
            self._calls_local += 1
        elif result.backend == "cloud":
            self._calls_cloud += 1
        self._total_latency_ms += result.latency_ms

        return LLMResponse(
            text=result.text,
            model=result.model,
            backend=result.backend,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=cost,
            latency_ms=result.latency_ms,
        )

    # -- Cost tracking ------------------------------------------------------

    def get_cost_report(self):
        """Return current session CostReport."""
        return self._cost_manager.get_report()

    def get_total_spent(self) -> float:
        return self._cost_manager.get_report().total_spent_usd

    def get_tokens_used(self) -> int:
        report = self._cost_manager.get_report()
        return report.total_input_tokens + report.total_output_tokens

    # -- Budget -------------------------------------------------------------

    def set_budget(self, max_usd: float) -> None:
        self._cost_manager.reset_budget(max_usd)
        self._cost_manager._strict = True

    def get_remaining_budget(self) -> Optional[float]:
        return self._cost_manager.remaining_budget

    # -- Intent parsing -----------------------------------------------------

    def parse_intent(self, user_input: str, system_prompt: str) -> Optional[Dict]:
        """Convenience: generate a response and attempt to parse it as JSON."""
        full_prompt = f"{system_prompt}\n\nUser input: {user_input}\n\nRespond with JSON only."
        resp = self.generate(full_prompt, task_type="intent_parsing")
        try:
            return json.loads(resp.text)
        except (json.JSONDecodeError, TypeError):
            return None

    # -- Summarization ------------------------------------------------------

    def summarize(self, text: str, max_length: int = 200) -> str:
        """Convenience: summarize text, routing to local when possible."""
        prompt = (
            f"Summarize the following text in at most {max_length} words. "
            f"Be concise and factual.\n\n{text}"
        )
        # Summarization is usually simple; use "summarize" task type
        # which the router scores as a COMPLEX_TYPE but we still let
        # the router decide based on length/mode
        resp = self.generate(prompt, task_type="summarize")
        return resp.text

    # -- Context assembly ---------------------------------------------------

    def generate_with_context(
        self,
        prompt: str,
        context_items: List[str],
        task_type: str = "general",
        max_context_tokens: int = _DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> LLMResponse:
        """Prepend context items to the prompt, truncating if needed."""
        # Estimate tokens: ~4 chars per token
        prompt_tokens = len(prompt) // 4
        available_tokens = max(max_context_tokens - prompt_tokens - 50, 0)  # 50 for formatting

        # Build context, respecting token budget (items in order = by relevance)
        context_parts: list[str] = []
        tokens_used = 0
        for item in context_items:
            item_tokens = len(item) // 4
            if tokens_used + item_tokens > available_tokens:
                # Truncate this item to fit remaining budget
                remaining_chars = (available_tokens - tokens_used) * 4
                if remaining_chars > 20:
                    context_parts.append(item[:remaining_chars])
                break
            context_parts.append(item)
            tokens_used += item_tokens

        # Assemble
        if context_parts:
            context_block = "\n\n".join(context_parts)
            full_prompt = f"Context:\n{context_block}\n\nQuestion: {prompt}"
        else:
            full_prompt = prompt

        return self.generate(full_prompt, task_type=task_type)

    # -- Configuration ------------------------------------------------------

    def set_local_model(self, model_name: str) -> None:
        self._router.set_local_model(model_name)

    def set_cloud_model(self, model_name: str) -> None:
        self._router.set_cloud_model(model_name)

    def set_privacy_mode(self, mode: PrivacyMode) -> None:
        self._privacy_mode = mode
        self._router._mode = mode

    def get_config(self) -> Dict:
        return {
            "privacy_mode": self._privacy_mode.value,
            "local_model": self._router._local_model,
            "cloud_model": self._router._cloud_model,
            "budget": self._cost_manager._budget,
            "hardware": self._hw_profile.to_dict(),
            "recommended_model": self._model_rec.model_name,
        }

    # -- Statistics ---------------------------------------------------------

    def get_stats(self) -> Dict:
        report = self._cost_manager.get_report()
        total_calls = self._calls_local + self._calls_cloud
        avg_latency = self._total_latency_ms / total_calls if total_calls > 0 else 0.0
        return {
            "total_calls": total_calls,
            "total_tokens": report.total_input_tokens + report.total_output_tokens,
            "total_cost_usd": report.total_spent_usd,
            "calls_local": self._calls_local,
            "calls_cloud": self._calls_cloud,
            "avg_latency_ms": avg_latency,
        }
