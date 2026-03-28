"""
Multi-provider LLM backends for IntentOS.
Supports: Anthropic, OpenAI, Gemini, Ollama, any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from core.inference.router import InferenceResult


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------

class LLMProvider(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    provider: LLMProvider
    api_key: str
    model: str
    base_url: Optional[str] = None
    display_name: str = ""

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = _DISPLAY_NAMES.get(self.provider, self.provider.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider.value,
            "api_key": self.api_key,
            "model": self.model,
            "base_url": self.base_url,
            "display_name": self.display_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProviderConfig:
        return cls(
            provider=LLMProvider(data["provider"]),
            api_key=data["api_key"],
            model=data["model"],
            base_url=data.get("base_url"),
            display_name=data.get("display_name", ""),
        )


_DISPLAY_NAMES: Dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "Anthropic (Claude)",
    LLMProvider.OPENAI: "OpenAI (GPT)",
    LLMProvider.GEMINI: "Google (Gemini)",
    LLMProvider.OLLAMA: "Ollama (Local)",
    LLMProvider.CUSTOM: "Custom Endpoint",
}


# ---------------------------------------------------------------------------
# Default models
# ---------------------------------------------------------------------------

DEFAULT_MODELS: Dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "claude-sonnet-4-20250514",
    LLMProvider.OPENAI: "gpt-4o",
    LLMProvider.GEMINI: "gemini-2.0-flash",
    LLMProvider.OLLAMA: "llama3.1:8b",
    LLMProvider.CUSTOM: "gpt-4o",
}


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

class AnthropicBackend:
    """Cloud backend wrapping the Anthropic Python SDK."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-20250514"):
        self._api_key = api_key
        self._default_model = default_model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed")
        return self._client

    def generate(self, prompt: str, model: str | None = None) -> InferenceResult:
        model = model or self._default_model
        client = self._ensure_client()
        start = time.monotonic()
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            text = response.content[0].text if response.content else ""
            return InferenceResult(
                text=text,
                model=model,
                backend="cloud",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return InferenceResult(
                text="",
                model=model,
                backend="cloud",
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed_ms,
                error=str(exc),
            )


class OpenAIBackend:
    """Cloud backend wrapping the OpenAI Python SDK."""

    def __init__(self, api_key: str, default_model: str = "gpt-4o"):
        self._api_key = api_key
        self._default_model = default_model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
            except ImportError:
                raise RuntimeError("openai package not installed")
        return self._client

    def generate(self, prompt: str, model: str | None = None) -> InferenceResult:
        model = model or self._default_model
        client = self._ensure_client()
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            choice = response.choices[0] if response.choices else None
            text = choice.message.content if choice and choice.message else ""
            usage = response.usage
            return InferenceResult(
                text=text or "",
                model=model,
                backend="cloud",
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return InferenceResult(
                text="",
                model=model,
                backend="cloud",
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed_ms,
                error=str(exc),
            )


class GeminiBackend:
    """Cloud backend wrapping the Google Generative AI SDK."""

    def __init__(self, api_key: str, default_model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._default_model = default_model
        self._configured = False

    def _ensure_configured(self) -> None:
        if not self._configured:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self._configured = True
            except ImportError:
                raise RuntimeError("google-generativeai package not installed")

    def generate(self, prompt: str, model: str | None = None) -> InferenceResult:
        model_name = model or self._default_model
        self._ensure_configured()
        start = time.monotonic()
        try:
            import google.generativeai as genai
            gmodel = genai.GenerativeModel(model_name)
            response = gmodel.generate_content(prompt)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            text = response.text if response.text else ""
            # Gemini usage metadata
            usage = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
            output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
            return InferenceResult(
                text=text,
                model=model_name,
                backend="cloud",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return InferenceResult(
                text="",
                model=model_name,
                backend="cloud",
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed_ms,
                error=str(exc),
            )


class OllamaBackend:
    """Local backend wrapping HTTP calls to Ollama."""

    def __init__(self, base_url: str = "http://localhost:11434", default_model: str = "llama3.1:8b"):
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    def generate(self, prompt: str, model: str | None = None) -> InferenceResult:
        model = model or self._default_model
        start = time.monotonic()
        try:
            import urllib.request
            import urllib.error

            payload = json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())

            elapsed_ms = int((time.monotonic() - start) * 1000)
            text = body.get("response", "")
            input_tokens = body.get("prompt_eval_count", len(prompt) // 4)
            output_tokens = body.get("eval_count", len(text) // 4)
            return InferenceResult(
                text=text,
                model=model,
                backend="local",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return InferenceResult(
                text="",
                model=model,
                backend="local",
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed_ms,
                error=str(exc),
            )


class CustomBackend:
    """OpenAI-compatible endpoint with a custom base_url."""

    def __init__(self, api_key: str, base_url: str, default_model: str = "gpt-4o"):
        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
            except ImportError:
                raise RuntimeError("openai package not installed")
        return self._client

    def generate(self, prompt: str, model: str | None = None) -> InferenceResult:
        model = model or self._default_model
        client = self._ensure_client()
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            choice = response.choices[0] if response.choices else None
            text = choice.message.content if choice and choice.message else ""
            usage = response.usage
            return InferenceResult(
                text=text or "",
                model=model,
                backend="cloud",
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return InferenceResult(
                text="",
                model=model,
                backend="cloud",
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed_ms,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_backend(config: ProviderConfig) -> Any:
    """Create the appropriate backend for the given provider config.

    Returns an object that implements generate(prompt, model) -> InferenceResult.
    Raises ValueError for invalid provider.
    """
    if config.provider == LLMProvider.ANTHROPIC:
        if not config.api_key:
            raise ValueError("api_key is required for Anthropic")
        return AnthropicBackend(api_key=config.api_key, default_model=config.model)

    if config.provider == LLMProvider.OPENAI:
        if not config.api_key:
            raise ValueError("api_key is required for OpenAI")
        return OpenAIBackend(api_key=config.api_key, default_model=config.model)

    if config.provider == LLMProvider.GEMINI:
        if not config.api_key:
            raise ValueError("api_key is required for Gemini")
        return GeminiBackend(api_key=config.api_key, default_model=config.model)

    if config.provider == LLMProvider.OLLAMA:
        base_url = config.base_url or "http://localhost:11434"
        return OllamaBackend(base_url=base_url, default_model=config.model)

    if config.provider == LLMProvider.CUSTOM:
        if not config.api_key:
            raise ValueError("api_key is required for Custom endpoint")
        if not config.base_url:
            raise ValueError("base_url is required for Custom endpoint")
        return CustomBackend(
            api_key=config.api_key,
            base_url=config.base_url,
            default_model=config.model,
        )

    raise ValueError(f"Unknown provider: {config.provider}")
