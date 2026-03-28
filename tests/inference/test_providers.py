"""Tests for multi-provider LLM backends (core/inference/providers.py).

All tests use mocks — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from core.inference.providers import (
    AnthropicBackend,
    CustomBackend,
    DEFAULT_MODELS,
    GeminiBackend,
    LLMProvider,
    OllamaBackend,
    OpenAIBackend,
    ProviderConfig,
    create_backend,
)
from core.inference.router import InferenceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_anthropic_response(text="hello", input_tokens=10, output_tokens=5):
    resp = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    resp.content = [content_block]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


def _mock_openai_response(text="hello", prompt_tokens=10, completion_tokens=5):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    resp.choices = [choice]
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    return resp


def _mock_gemini_response(text="hello", prompt_tokens=10, output_tokens=5):
    resp = MagicMock()
    resp.text = text
    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = output_tokens
    resp.usage_metadata = usage
    return resp


# ---------------------------------------------------------------------------
# 1. AnthropicBackend.generate()
# ---------------------------------------------------------------------------

class TestAnthropicBackend:
    @patch("core.inference.providers.AnthropicBackend._ensure_client")
    def test_generate_returns_inference_result(self, mock_ensure):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response("Hi there")
        mock_ensure.return_value = client

        backend = AnthropicBackend(api_key="sk-test")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.text == "Hi there"
        assert result.backend == "cloud"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.error is None

    @patch("core.inference.providers.AnthropicBackend._ensure_client")
    def test_generate_error_returns_result_with_error(self, mock_ensure):
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("API down")
        mock_ensure.return_value = client

        backend = AnthropicBackend(api_key="sk-test")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.text == ""
        assert result.error is not None
        assert "API down" in result.error


# ---------------------------------------------------------------------------
# 2. OpenAIBackend.generate()
# ---------------------------------------------------------------------------

class TestOpenAIBackend:
    @patch("core.inference.providers.OpenAIBackend._ensure_client")
    def test_generate_returns_inference_result(self, mock_ensure):
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response("GPT says hi")
        mock_ensure.return_value = client

        backend = OpenAIBackend(api_key="sk-test")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.text == "GPT says hi"
        assert result.backend == "cloud"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.error is None

    @patch("core.inference.providers.OpenAIBackend._ensure_client")
    def test_generate_error_returns_result_with_error(self, mock_ensure):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("Rate limited")
        mock_ensure.return_value = client

        backend = OpenAIBackend(api_key="sk-test")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.error is not None
        assert "Rate limited" in result.error


# ---------------------------------------------------------------------------
# 3. GeminiBackend.generate()
# ---------------------------------------------------------------------------

class TestGeminiBackend:
    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_generate_returns_inference_result(self, mock_configure, mock_model_cls):
        mock_model = MagicMock()
        mock_model.generate_content.return_value = _mock_gemini_response("Gemini says hi")
        mock_model_cls.return_value = mock_model

        backend = GeminiBackend(api_key="test-key")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.text == "Gemini says hi"
        assert result.backend == "cloud"
        assert result.error is None

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_generate_error_returns_result_with_error(self, mock_configure, mock_model_cls):
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("Quota exceeded")
        mock_model_cls.return_value = mock_model

        backend = GeminiBackend(api_key="test-key")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.error is not None
        assert "Quota exceeded" in result.error


# ---------------------------------------------------------------------------
# 4. OllamaBackend.generate()
# ---------------------------------------------------------------------------

class TestOllamaBackend:
    @patch("urllib.request.urlopen")
    def test_generate_returns_inference_result(self, mock_urlopen):
        body = json.dumps({
            "response": "Ollama says hi",
            "prompt_eval_count": 8,
            "eval_count": 4,
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        backend = OllamaBackend()
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.text == "Ollama says hi"
        assert result.backend == "local"
        assert result.input_tokens == 8
        assert result.output_tokens == 4
        assert result.error is None

    @patch("urllib.request.urlopen")
    def test_generate_error_returns_result_with_error(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionError("Connection refused")

        backend = OllamaBackend()
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.error is not None
        assert "Connection refused" in result.error


# ---------------------------------------------------------------------------
# 5. CustomBackend.generate() with base_url
# ---------------------------------------------------------------------------

class TestCustomBackend:
    @patch("core.inference.providers.CustomBackend._ensure_client")
    def test_generate_returns_inference_result(self, mock_ensure):
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response("Custom says hi")
        mock_ensure.return_value = client

        backend = CustomBackend(api_key="sk-test", base_url="https://my-llm.example.com/v1")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.text == "Custom says hi"
        assert result.backend == "cloud"
        assert result.error is None

    @patch("core.inference.providers.CustomBackend._ensure_client")
    def test_generate_error_returns_result_with_error(self, mock_ensure):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("Endpoint unreachable")
        mock_ensure.return_value = client

        backend = CustomBackend(api_key="sk-test", base_url="https://my-llm.example.com/v1")
        result = backend.generate("Say hi")

        assert isinstance(result, InferenceResult)
        assert result.error is not None
        assert "Endpoint unreachable" in result.error


# ---------------------------------------------------------------------------
# 6. create_backend() factory
# ---------------------------------------------------------------------------

class TestCreateBackend:
    def test_creates_anthropic_backend(self):
        config = ProviderConfig(provider=LLMProvider.ANTHROPIC, api_key="sk-test", model="claude-sonnet-4-20250514")
        backend = create_backend(config)
        assert isinstance(backend, AnthropicBackend)

    def test_creates_openai_backend(self):
        config = ProviderConfig(provider=LLMProvider.OPENAI, api_key="sk-test", model="gpt-4o")
        backend = create_backend(config)
        assert isinstance(backend, OpenAIBackend)

    def test_creates_gemini_backend(self):
        config = ProviderConfig(provider=LLMProvider.GEMINI, api_key="test-key", model="gemini-2.0-flash")
        backend = create_backend(config)
        assert isinstance(backend, GeminiBackend)

    def test_creates_ollama_backend(self):
        config = ProviderConfig(provider=LLMProvider.OLLAMA, api_key="", model="llama3.1:8b")
        backend = create_backend(config)
        assert isinstance(backend, OllamaBackend)

    def test_creates_custom_backend(self):
        config = ProviderConfig(
            provider=LLMProvider.CUSTOM,
            api_key="sk-test",
            model="gpt-4o",
            base_url="https://my-llm.example.com/v1",
        )
        backend = create_backend(config)
        assert isinstance(backend, CustomBackend)


# ---------------------------------------------------------------------------
# 7. LLMProvider enum has all 5 values
# ---------------------------------------------------------------------------

class TestLLMProviderEnum:
    def test_has_all_five_values(self):
        expected = {"anthropic", "openai", "gemini", "ollama", "custom"}
        actual = {p.value for p in LLMProvider}
        assert actual == expected

    def test_enum_members(self):
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.GEMINI.value == "gemini"
        assert LLMProvider.OLLAMA.value == "ollama"
        assert LLMProvider.CUSTOM.value == "custom"


# ---------------------------------------------------------------------------
# 8. ProviderConfig serialization round-trip
# ---------------------------------------------------------------------------

class TestProviderConfigSerialization:
    def test_round_trip(self):
        config = ProviderConfig(
            provider=LLMProvider.OPENAI,
            api_key="sk-test-123",
            model="gpt-4o",
            base_url=None,
            display_name="OpenAI (GPT)",
        )
        data = config.to_dict()
        restored = ProviderConfig.from_dict(data)

        assert restored.provider == config.provider
        assert restored.api_key == config.api_key
        assert restored.model == config.model
        assert restored.base_url == config.base_url
        assert restored.display_name == config.display_name

    def test_round_trip_with_base_url(self):
        config = ProviderConfig(
            provider=LLMProvider.CUSTOM,
            api_key="key",
            model="my-model",
            base_url="https://example.com/v1",
        )
        data = config.to_dict()
        restored = ProviderConfig.from_dict(data)
        assert restored.base_url == "https://example.com/v1"

    def test_json_round_trip(self):
        config = ProviderConfig(
            provider=LLMProvider.GEMINI,
            api_key="gem-key",
            model="gemini-2.0-flash",
        )
        json_str = json.dumps(config.to_dict())
        data = json.loads(json_str)
        restored = ProviderConfig.from_dict(data)
        assert restored.provider == LLMProvider.GEMINI


# ---------------------------------------------------------------------------
# 9. DEFAULT_MODELS has all providers
# ---------------------------------------------------------------------------

class TestDefaultModels:
    def test_has_all_providers(self):
        for provider in LLMProvider:
            assert provider in DEFAULT_MODELS, f"Missing default model for {provider}"

    def test_models_are_non_empty_strings(self):
        for provider, model in DEFAULT_MODELS.items():
            assert isinstance(model, str)
            assert len(model) > 0


# ---------------------------------------------------------------------------
# 10. Backend error handling
# ---------------------------------------------------------------------------

class TestBackendErrorHandling:
    @patch("core.inference.providers.AnthropicBackend._ensure_client")
    def test_anthropic_error_returns_error_field(self, mock_ensure):
        client = MagicMock()
        client.messages.create.side_effect = Exception("auth failed")
        mock_ensure.return_value = client

        result = AnthropicBackend(api_key="bad").generate("test")
        assert result.error is not None
        assert result.text == ""

    @patch("core.inference.providers.OpenAIBackend._ensure_client")
    def test_openai_error_returns_error_field(self, mock_ensure):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("invalid key")
        mock_ensure.return_value = client

        result = OpenAIBackend(api_key="bad").generate("test")
        assert result.error is not None
        assert result.text == ""

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_gemini_error_returns_error_field(self, mock_configure, mock_model_cls):
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("quota exceeded")
        mock_model_cls.return_value = mock_model

        result = GeminiBackend(api_key="bad").generate("test")
        assert result.error is not None
        assert result.text == ""

    @patch("urllib.request.urlopen")
    def test_ollama_error_returns_error_field(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("connection refused")

        result = OllamaBackend().generate("test")
        assert result.error is not None
        assert result.text == ""

    @patch("core.inference.providers.CustomBackend._ensure_client")
    def test_custom_error_returns_error_field(self, mock_ensure):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("timeout")
        mock_ensure.return_value = client

        result = CustomBackend(api_key="bad", base_url="http://x").generate("test")
        assert result.error is not None
        assert result.text == ""


# ---------------------------------------------------------------------------
# 11. Invalid provider -> ValueError
# ---------------------------------------------------------------------------

class TestInvalidProvider:
    def test_invalid_provider_string_raises_value_error(self):
        with pytest.raises(ValueError):
            LLMProvider("nonexistent_provider")

    def test_create_backend_missing_api_key_anthropic(self):
        config = ProviderConfig(provider=LLMProvider.ANTHROPIC, api_key="", model="claude-sonnet-4-20250514")
        with pytest.raises(ValueError, match="api_key is required"):
            create_backend(config)

    def test_create_backend_missing_api_key_openai(self):
        config = ProviderConfig(provider=LLMProvider.OPENAI, api_key="", model="gpt-4o")
        with pytest.raises(ValueError, match="api_key is required"):
            create_backend(config)

    def test_create_backend_missing_api_key_gemini(self):
        config = ProviderConfig(provider=LLMProvider.GEMINI, api_key="", model="gemini-2.0-flash")
        with pytest.raises(ValueError, match="api_key is required"):
            create_backend(config)


# ---------------------------------------------------------------------------
# 12. Missing api_key -> error
# ---------------------------------------------------------------------------

class TestMissingApiKey:
    def test_custom_missing_api_key(self):
        config = ProviderConfig(
            provider=LLMProvider.CUSTOM,
            api_key="",
            model="gpt-4o",
            base_url="http://example.com/v1",
        )
        with pytest.raises(ValueError, match="api_key is required"):
            create_backend(config)

    def test_custom_missing_base_url(self):
        config = ProviderConfig(
            provider=LLMProvider.CUSTOM,
            api_key="sk-test",
            model="gpt-4o",
            base_url=None,
        )
        with pytest.raises(ValueError, match="base_url is required"):
            create_backend(config)

    def test_ollama_no_api_key_is_fine(self):
        """Ollama does not require an API key."""
        config = ProviderConfig(provider=LLMProvider.OLLAMA, api_key="", model="llama3.1:8b")
        backend = create_backend(config)
        assert isinstance(backend, OllamaBackend)
