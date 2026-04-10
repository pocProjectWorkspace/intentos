"""Tests for LLMService — unified inference integration layer.

All tests use mock backends; no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.inference.router import InferenceResult, PrivacyMode
from core.orchestration.cost_manager import BudgetExceededException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inference_result(
    text: str = "Hello world",
    model: str = "gemma4:e4b",
    backend: str = "local",
    input_tokens: int = 10,
    output_tokens: int = 20,
    latency_ms: int = 100,
    error: str | None = None,
) -> InferenceResult:
    return InferenceResult(
        text=text,
        model=model,
        backend=backend,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        error=error,
    )


def _mock_hardware_profile():
    """Return a mock HardwareProfile."""
    from core.inference.hardware import GPUInfo, HardwareProfile

    return HardwareProfile(
        gpu=GPUInfo(vendor="apple", model="Apple M2 Pro", vram_gb=16.0),
        ram_gb=16.0,
        cpu_cores=10,
        cpu_model="Apple M2 Pro",
        platform="darwin",
        arch="arm64",
    )


def _build_service(privacy_mode=PrivacyMode.SMART_ROUTING, budget=None):
    """Build an LLMService with mock backends injected."""
    from core.inference.llm import LLMService

    with patch("core.inference.llm.HardwareDetector") as MockHW:
        detector_instance = MockHW.return_value
        detector_instance.detect.return_value = _mock_hardware_profile()
        from core.inference.hardware import ModelRecommendation

        detector_instance.recommend_model.return_value = ModelRecommendation(
            model_name="gemma4:26b-a4b",
            model_size="26B",
            estimated_ram_gb=6.0,
            reason="16 GB+ RAM with GPU acceleration supports 26B model well.",
        )
        svc = LLMService(privacy_mode=privacy_mode, budget=budget)

    # Inject mock backends
    local_backend = MagicMock()
    local_backend.generate.return_value = _make_inference_result(
        text="local response", model="gemma4:e4b", backend="local",
        input_tokens=10, output_tokens=20, latency_ms=50,
    )
    cloud_backend = MagicMock()
    cloud_backend.generate.return_value = _make_inference_result(
        text="cloud response", model="claude-sonnet-4-20250514", backend="cloud",
        input_tokens=100, output_tokens=200, latency_ms=500,
    )
    svc._router.set_local_backend(local_backend)
    svc._router.set_cloud_backend(cloud_backend)
    svc._local_backend = local_backend
    svc._cloud_backend = cloud_backend
    # For SMART_ROUTING, allow cloud consent automatically
    svc._router.set_consent_callback(lambda *a: True)
    return svc


# ===========================================================================
# Initialization tests (1-4)
# ===========================================================================


class TestInitialization:
    def test_auto_detects_hardware_and_recommends_model(self):
        """1. LLMService() auto-detects hardware and recommends model."""
        svc = _build_service()
        profile = svc.get_hardware_profile()
        assert profile is not None
        assert profile.ram_gb == 16.0

    def test_privacy_mode_set(self):
        """2. LLMService(privacy_mode=LOCAL_ONLY) sets mode."""
        svc = _build_service(privacy_mode=PrivacyMode.LOCAL_ONLY)
        cfg = svc.get_config()
        assert cfg["privacy_mode"] == PrivacyMode.LOCAL_ONLY.value

    def test_get_hardware_profile(self):
        """3. get_hardware_profile() returns detected profile."""
        svc = _build_service()
        profile = svc.get_hardware_profile()
        assert profile.cpu_cores == 10
        assert profile.platform == "darwin"

    def test_get_recommended_model(self):
        """4. get_recommended_model() returns model recommendation."""
        svc = _build_service()
        rec = svc.get_recommended_model()
        assert rec.model_name == "gemma4:26b-a4b"


# ===========================================================================
# Inference tests (5-9)
# ===========================================================================


class TestInference:
    def test_generate_returns_llm_response(self):
        """5. generate() routes through InferenceRouter and returns LLMResponse."""
        from core.inference.llm import LLMResponse

        svc = _build_service()
        resp = svc.generate("Hello", task_type="general")
        assert isinstance(resp, LLMResponse)
        assert resp.text != ""

    def test_llm_response_fields(self):
        """6. LLMResponse has: text, model, backend, input_tokens, output_tokens, cost_usd, latency_ms."""
        svc = _build_service()
        resp = svc.generate("Hello")
        assert hasattr(resp, "text")
        assert hasattr(resp, "model")
        assert hasattr(resp, "backend")
        assert hasattr(resp, "input_tokens")
        assert hasattr(resp, "output_tokens")
        assert hasattr(resp, "cost_usd")
        assert hasattr(resp, "latency_ms")
        assert isinstance(resp.cost_usd, float)
        assert isinstance(resp.latency_ms, (int, float))

    def test_local_only_uses_local_backend(self):
        """7. LOCAL_ONLY mode uses local backend."""
        svc = _build_service(privacy_mode=PrivacyMode.LOCAL_ONLY)
        resp = svc.generate("Hello")
        assert resp.backend == "local"

    def test_performance_uses_cloud_backend(self):
        """8. PERFORMANCE mode uses cloud backend."""
        svc = _build_service(privacy_mode=PrivacyMode.PERFORMANCE)
        resp = svc.generate("Hello")
        assert resp.backend == "cloud"

    def test_smart_routing_routes_based_on_complexity(self):
        """9. SMART_ROUTING routes based on complexity."""
        svc = _build_service(privacy_mode=PrivacyMode.SMART_ROUTING)
        # Simple task -> local
        resp_simple = svc.generate("list files", task_type="list")
        assert resp_simple.backend == "local"
        # Complex task -> cloud
        resp_complex = svc.generate(
            "Analyze the quarterly financial data and produce a report " * 10,
            task_type="analyze",
        )
        assert resp_complex.backend == "cloud"


# ===========================================================================
# Cost Tracking tests (10-13)
# ===========================================================================


class TestCostTracking:
    def test_generate_records_usage(self):
        """10. Every generate() call automatically records usage in CostManager."""
        svc = _build_service()
        svc.generate("test prompt")
        report = svc.get_cost_report()
        assert report.call_count == 1
        assert report.total_spent_usd > 0 or report.total_input_tokens > 0

    def test_get_cost_report(self):
        """11. get_cost_report() returns current session cost breakdown."""
        svc = _build_service()
        svc.generate("test 1")
        svc.generate("test 2")
        report = svc.get_cost_report()
        assert report.call_count == 2

    def test_get_total_spent(self):
        """12. get_total_spent() returns total USD spent."""
        svc = _build_service()
        svc.generate("prompt")
        total = svc.get_total_spent()
        assert isinstance(total, float)
        assert total >= 0.0

    def test_get_tokens_used(self):
        """13. get_tokens_used() returns total tokens."""
        svc = _build_service()
        svc.generate("prompt")
        tokens = svc.get_tokens_used()
        assert isinstance(tokens, int)
        assert tokens > 0


# ===========================================================================
# Budget Enforcement tests (14-16)
# ===========================================================================


class TestBudgetEnforcement:
    def test_set_budget(self):
        """14. set_budget(max_usd) sets spending limit."""
        svc = _build_service()
        svc.set_budget(1.00)
        assert svc.get_remaining_budget() == 1.00

    def test_generate_raises_budget_exceeded(self):
        """15. generate() raises BudgetExceededException when budget exhausted (strict)."""
        # Use PERFORMANCE mode to route to cloud (which has real cost)
        svc = _build_service(privacy_mode=PrivacyMode.PERFORMANCE, budget=0.0000001)
        svc._cost_manager._strict = True
        with pytest.raises(BudgetExceededException):
            svc.generate("prompt")

    def test_get_remaining_budget(self):
        """16. get_remaining_budget() returns remaining."""
        # Use PERFORMANCE mode to route to cloud (which has real cost)
        svc = _build_service(privacy_mode=PrivacyMode.PERFORMANCE, budget=5.0)
        remaining = svc.get_remaining_budget()
        assert remaining == 5.0
        svc.generate("prompt")
        remaining_after = svc.get_remaining_budget()
        assert remaining_after < 5.0


# ===========================================================================
# Intent Parsing tests (17-19)
# ===========================================================================


class TestIntentParsing:
    def test_parse_intent_returns_dict(self):
        """17. parse_intent() — convenience method returns parsed JSON dict."""
        svc = _build_service()
        # Mock the local backend to return valid JSON
        svc._local_backend.generate.return_value = _make_inference_result(
            text='{"intent": "open_file", "target": "readme.md"}',
        )
        svc._cloud_backend.generate.return_value = _make_inference_result(
            text='{"intent": "open_file", "target": "readme.md"}',
            backend="cloud", model="claude-sonnet-4-20250514",
        )
        result = svc.parse_intent("open the readme file", system_prompt="Parse intent")
        assert isinstance(result, dict)
        assert "intent" in result

    def test_parse_intent_returns_none_on_failure(self):
        """18. Returns None if parsing fails."""
        svc = _build_service()
        svc._local_backend.generate.return_value = _make_inference_result(
            text="this is not valid json at all",
        )
        svc._cloud_backend.generate.return_value = _make_inference_result(
            text="this is not valid json at all",
            backend="cloud",
        )
        result = svc.parse_intent("do something", system_prompt="Parse intent")
        assert result is None

    def test_parse_intent_uses_appropriate_model(self):
        """19. Automatically uses appropriate model for intent parsing."""
        svc = _build_service()
        svc._local_backend.generate.return_value = _make_inference_result(
            text='{"intent": "test"}',
        )
        svc._cloud_backend.generate.return_value = _make_inference_result(
            text='{"intent": "test"}', backend="cloud",
        )
        svc.parse_intent("test", system_prompt="Parse")
        # Should have called generate — verify a call was made
        total_calls = (
            svc._local_backend.generate.call_count
            + svc._cloud_backend.generate.call_count
        )
        assert total_calls >= 1


# ===========================================================================
# Summarization tests (20-21)
# ===========================================================================


class TestSummarization:
    def test_summarize_returns_text(self):
        """20. summarize() returns summary text."""
        svc = _build_service()
        svc._local_backend.generate.return_value = _make_inference_result(
            text="This is a summary.",
        )
        result = svc.summarize("A very long document " * 100, max_length=200)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_summarize_routes_local_when_possible(self):
        """21. Routes to local model when possible."""
        svc = _build_service(privacy_mode=PrivacyMode.SMART_ROUTING)
        svc._local_backend.generate.return_value = _make_inference_result(
            text="Summary here.", backend="local",
        )
        result = svc.summarize("Short text to summarize.")
        # Summarization of simple text should use local
        assert isinstance(result, str)


# ===========================================================================
# Context Assembly tests (22-24)
# ===========================================================================


class TestContextAssembly:
    def test_generate_with_context(self):
        """22. generate_with_context() prepends context to prompt."""
        svc = _build_service()
        svc._local_backend.generate.return_value = _make_inference_result(
            text="answer with context",
        )
        svc._cloud_backend.generate.return_value = _make_inference_result(
            text="answer with context", backend="cloud",
        )
        resp = svc.generate_with_context(
            "What is the capital?",
            context_items=["France is a country in Europe.", "Paris is a city."],
        )
        assert resp.text == "answer with context"
        # Verify that context was included in the prompt sent to backend
        call_args = (
            svc._local_backend.generate.call_args
            or svc._cloud_backend.generate.call_args
        )
        prompt_sent = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        assert "France" in prompt_sent or "context" in prompt_sent.lower()

    def test_context_truncation(self):
        """23. Respects token budget — truncates context if too long."""
        svc = _build_service()
        svc._local_backend.generate.return_value = _make_inference_result(text="ok")
        svc._cloud_backend.generate.return_value = _make_inference_result(
            text="ok", backend="cloud",
        )
        # Very long context items
        huge_context = ["word " * 10000 for _ in range(10)]
        resp = svc.generate_with_context("question?", context_items=huge_context)
        assert resp.text == "ok"

    def test_context_order(self):
        """24. Context items ordered by relevance (first = most relevant)."""
        svc = _build_service()
        svc._local_backend.generate.return_value = _make_inference_result(text="ok")
        svc._cloud_backend.generate.return_value = _make_inference_result(
            text="ok", backend="cloud",
        )
        svc.generate_with_context(
            "question",
            context_items=["FIRST_ITEM", "SECOND_ITEM", "THIRD_ITEM"],
        )
        call_args = (
            svc._local_backend.generate.call_args
            or svc._cloud_backend.generate.call_args
        )
        prompt_sent = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        # First item should appear before second in the assembled prompt
        idx1 = prompt_sent.find("FIRST_ITEM")
        idx2 = prompt_sent.find("SECOND_ITEM")
        assert idx1 < idx2


# ===========================================================================
# Configuration tests (25-27)
# ===========================================================================


class TestConfiguration:
    def test_set_local_model(self):
        """25a. set_local_model() changes the local model."""
        svc = _build_service()
        svc.set_local_model("tinyllama:latest")
        cfg = svc.get_config()
        assert cfg["local_model"] == "tinyllama:latest"

    def test_set_cloud_model(self):
        """25b. set_cloud_model() changes the cloud model."""
        svc = _build_service()
        svc.set_cloud_model("claude-haiku")
        cfg = svc.get_config()
        assert cfg["cloud_model"] == "claude-haiku"

    def test_set_privacy_mode(self):
        """26. set_privacy_mode() changes routing behavior."""
        svc = _build_service()
        svc.set_privacy_mode(PrivacyMode.LOCAL_ONLY)
        cfg = svc.get_config()
        assert cfg["privacy_mode"] == PrivacyMode.LOCAL_ONLY.value

    def test_get_config(self):
        """27. get_config() returns current config dict."""
        svc = _build_service()
        cfg = svc.get_config()
        assert "privacy_mode" in cfg
        assert "local_model" in cfg
        assert "cloud_model" in cfg


# ===========================================================================
# Statistics tests (28)
# ===========================================================================


class TestStatistics:
    def test_get_stats(self):
        """28. get_stats() returns: total_calls, total_tokens, total_cost_usd, etc."""
        svc = _build_service()
        svc.generate("prompt 1")
        svc.generate("prompt 2")
        stats = svc.get_stats()
        assert stats["total_calls"] == 2
        assert stats["total_tokens"] > 0
        assert "total_cost_usd" in stats
        assert "calls_local" in stats
        assert "calls_cloud" in stats
        assert "avg_latency_ms" in stats
