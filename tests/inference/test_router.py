"""Tests for InferenceRouter — Phase 2C.1 TDD."""

import pytest
from core.inference.router import (
    InferenceBackend,
    InferenceError,
    InferenceResult,
    InferenceRouter,
    PrivacyMode,
)


# ---------------------------------------------------------------------------
# Mock backends
# ---------------------------------------------------------------------------

class MockLocalBackend:
    def generate(self, prompt, model=None):
        return InferenceResult(
            text="local response",
            model=model or "gemma4:e4b",
            backend="local",
            input_tokens=10,
            output_tokens=20,
            latency_ms=50,
        )


class MockCloudBackend:
    def generate(self, prompt, model=None):
        return InferenceResult(
            text="cloud response",
            model=model or "claude-sonnet-4",
            backend="cloud",
            input_tokens=10,
            output_tokens=20,
            latency_ms=200,
        )


class FailingBackend:
    def generate(self, prompt, model=None):
        raise Exception("Backend unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _router_with_backends(mode=PrivacyMode.SMART_ROUTING, **kw):
    r = InferenceRouter(mode=mode, **kw)
    r.set_local_backend(MockLocalBackend())
    r.set_cloud_backend(MockCloudBackend())
    return r


# ===================================================================
# 1. PrivacyMode enum
# ===================================================================

class TestPrivacyMode:
    def test_three_modes_exist(self):
        """Test 1: Three modes — LOCAL_ONLY, SMART_ROUTING, PERFORMANCE."""
        assert PrivacyMode.LOCAL_ONLY
        assert PrivacyMode.SMART_ROUTING
        assert PrivacyMode.PERFORMANCE
        assert len(PrivacyMode) == 3


# ===================================================================
# 2. InferenceResult model
# ===================================================================

class TestInferenceResult:
    def test_fields(self):
        """Test 2: InferenceResult contains all required fields."""
        r = InferenceResult(
            text="hello",
            model="gemma4:e4b",
            backend="local",
            input_tokens=5,
            output_tokens=10,
            latency_ms=42,
        )
        assert r.text == "hello"
        assert r.model == "gemma4:e4b"
        assert r.backend == "local"
        assert r.input_tokens == 5
        assert r.output_tokens == 10
        assert r.latency_ms == 42


# ===================================================================
# 3-8. Routing by Privacy Mode
# ===================================================================

class TestRoutingByPrivacyMode:
    def test_local_only_routes_to_local(self):
        """Test 3: LOCAL_ONLY always routes to local backend."""
        router = _router_with_backends(PrivacyMode.LOCAL_ONLY)
        result = router.route("hello")
        assert result.backend == "local"

    def test_local_only_never_uses_cloud_for_complex(self):
        """Test 4: LOCAL_ONLY never touches cloud even for complex tasks."""
        router = _router_with_backends(PrivacyMode.LOCAL_ONLY)
        result = router.route("Summarize all research papers on quantum computing from the last decade", task_type="research")
        assert result.backend == "local"

    def test_performance_routes_to_cloud(self):
        """Test 5: PERFORMANCE always routes to cloud backend."""
        router = _router_with_backends(PrivacyMode.PERFORMANCE)
        result = router.route("hello")
        assert result.backend == "cloud"

    def test_performance_never_uses_local(self):
        """Test 6: PERFORMANCE never uses local even for simple tasks."""
        router = _router_with_backends(PrivacyMode.PERFORMANCE)
        result = router.route("list files", task_type="list")
        assert result.backend == "cloud"

    def test_smart_routing_simple_to_local(self):
        """Test 7: SMART_ROUTING — simple task routes to local."""
        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        result = router.route("list files", task_type="list")
        assert result.backend == "local"

    def test_smart_routing_complex_to_cloud_with_consent(self):
        """Test 8: SMART_ROUTING — complex task routes to cloud (with consent)."""
        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        router.set_consent_callback(lambda *_: True)
        result = router.route(
            "Summarize all research papers on quantum computing from the last decade",
            task_type="research",
        )
        assert result.backend == "cloud"


# ===================================================================
# 9-12. Complexity Scoring
# ===================================================================

class TestComplexityScoring:
    def test_score_returns_float_in_range(self):
        """Test 9: score_task returns float between 0.0 and 1.0."""
        router = _router_with_backends()
        score = router.score_task("hello", "list")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_short_simple_low_score(self):
        """Test 10: Short prompt + simple task_type gives low score."""
        router = _router_with_backends()
        score = router.score_task("list files", "list")
        assert score < 0.4

    def test_long_complex_high_score(self):
        """Test 11: Long prompt + complex task_type gives high score."""
        router = _router_with_backends()
        long_prompt = "Please analyze the following dataset and provide insights: " + "data " * 200
        score = router.score_task(long_prompt, "analyze")
        assert score > 0.4

    def test_local_threshold_configurable(self):
        """Test 12: LOCAL_THRESHOLD configurable (default 0.4)."""
        router = _router_with_backends(local_threshold=0.8)
        router.set_consent_callback(lambda *_: True)
        # With a high threshold, even medium tasks stay local
        result = router.route("summarize this short text", task_type="summarize")
        assert result.backend == "local"


# ===================================================================
# 13-17. Backend Management
# ===================================================================

class TestBackendManagement:
    def test_set_local_backend(self):
        """Test 13: set_local_backend registers local backend."""
        router = InferenceRouter()
        backend = MockLocalBackend()
        router.set_local_backend(backend)
        # Should not raise
        router.set_cloud_backend(MockCloudBackend())
        result = router.route("hello", task_type="list")
        assert result.backend == "local"

    def test_set_cloud_backend(self):
        """Test 14: set_cloud_backend registers cloud backend."""
        router = InferenceRouter(mode=PrivacyMode.PERFORMANCE)
        backend = MockCloudBackend()
        router.set_cloud_backend(backend)
        result = router.route("hello")
        assert result.backend == "cloud"

    def test_no_local_backend_local_only_raises(self):
        """Test 15: No local backend + LOCAL_ONLY raises InferenceError."""
        router = InferenceRouter(mode=PrivacyMode.LOCAL_ONLY)
        with pytest.raises(InferenceError):
            router.route("hello")

    def test_no_cloud_backend_performance_raises(self):
        """Test 16: No cloud backend + PERFORMANCE raises InferenceError."""
        router = InferenceRouter(mode=PrivacyMode.PERFORMANCE)
        with pytest.raises(InferenceError):
            router.route("hello")

    def test_no_cloud_smart_routing_falls_back_to_local(self):
        """Test 17: No cloud backend + SMART_ROUTING falls back to local for all tasks."""
        router = InferenceRouter(mode=PrivacyMode.SMART_ROUTING)
        router.set_local_backend(MockLocalBackend())
        router.set_consent_callback(lambda *_: True)
        # Even a complex task should fall back to local when no cloud backend
        result = router.route(
            "Summarize all research papers on quantum computing",
            task_type="research",
        )
        assert result.backend == "local"


# ===================================================================
# 18-21. Consent Flow
# ===================================================================

class TestConsentFlow:
    def test_consent_callback_called_before_cloud(self):
        """Test 18: consent_callback is called before routing to cloud."""
        called = {"count": 0}

        def cb(summary, tokens, task_type):
            called["count"] += 1
            return True

        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        router.set_consent_callback(cb)
        router.route("Analyze this very long text " * 50, task_type="analyze")
        assert called["count"] == 1

    def test_consent_callback_false_falls_back_to_local(self):
        """Test 19: consent_callback returns False -> falls back to local."""
        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        router.set_consent_callback(lambda *_: False)
        result = router.route("Analyze this very long text " * 50, task_type="analyze")
        assert result.backend == "local"

    def test_consent_callback_none_defaults_to_local(self):
        """Test 20: consent_callback is None -> defaults to local (safe default)."""
        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        # No consent callback set — should default to local
        result = router.route("Analyze this very long text " * 50, task_type="analyze")
        assert result.backend == "local"

    def test_consent_callback_receives_correct_args(self):
        """Test 21: consent_callback receives prompt summary, estimated tokens, task_type."""
        received = {}

        def cb(summary, tokens, task_type):
            received["summary"] = summary
            received["tokens"] = tokens
            received["task_type"] = task_type
            return True

        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        router.set_consent_callback(cb)
        prompt = "Analyze this text about climate change impacts on global agriculture"
        router.route(prompt * 5, task_type="analyze")

        assert isinstance(received["summary"], str)
        assert len(received["summary"]) <= 100
        assert isinstance(received["tokens"], int)
        assert received["task_type"] == "analyze"


# ===================================================================
# 22-24. Backend Protocol
# ===================================================================

class TestBackendProtocol:
    def test_backend_generate_signature(self):
        """Test 22: Backend must implement generate(prompt, model=None) -> InferenceResult."""
        backend = MockLocalBackend()
        result = backend.generate("hello", model="test-model")
        assert isinstance(result, InferenceResult)

    def test_local_backend_uses_local_model(self):
        """Test 23: Local backend uses model from local_model setting."""
        router = _router_with_backends(PrivacyMode.LOCAL_ONLY)
        router.set_local_model("custom-local")
        result = router.route("hello")
        assert result.model == "custom-local"

    def test_cloud_backend_uses_cloud_model(self):
        """Test 24: Cloud backend uses model from cloud_model setting."""
        router = _router_with_backends(PrivacyMode.PERFORMANCE)
        router.set_cloud_model("custom-cloud")
        result = router.route("hello")
        assert result.model == "custom-cloud"


# ===================================================================
# 25-27. Model Configuration
# ===================================================================

class TestModelConfiguration:
    def test_default_local_model(self):
        """Test 25: Default local model is gemma4:e4b."""
        router = _router_with_backends(PrivacyMode.LOCAL_ONLY)
        result = router.route("hello")
        assert result.model == "gemma4:e4b"

    def test_default_cloud_model(self):
        """Test 26: Default cloud model is claude-sonnet-4-20250514."""
        router = _router_with_backends(PrivacyMode.PERFORMANCE)
        result = router.route("hello")
        assert result.model == "claude-sonnet-4-20250514"

    def test_models_configurable(self):
        """Test 27: Models configurable via set_local_model / set_cloud_model."""
        router = _router_with_backends(PrivacyMode.LOCAL_ONLY)
        router.set_local_model("llama3")
        result = router.route("hello")
        assert result.model == "llama3"

        router2 = _router_with_backends(PrivacyMode.PERFORMANCE)
        router2.set_cloud_model("gpt-4o")
        result2 = router2.route("hello")
        assert result2.model == "gpt-4o"


# ===================================================================
# 28-30. Fallback
# ===================================================================

class TestFallback:
    def test_local_fails_smart_routing_falls_back_to_cloud(self):
        """Test 28: Local fails + SMART_ROUTING falls back to cloud (with consent)."""
        router = InferenceRouter(mode=PrivacyMode.SMART_ROUTING)
        router.set_local_backend(FailingBackend())
        router.set_cloud_backend(MockCloudBackend())
        router.set_consent_callback(lambda *_: True)
        result = router.route("list files", task_type="list")
        assert result.backend == "cloud"

    def test_cloud_fails_returns_error_result(self):
        """Test 29: Cloud fails returns error InferenceResult (never crash)."""
        router = InferenceRouter(mode=PrivacyMode.PERFORMANCE)
        router.set_cloud_backend(FailingBackend())
        result = router.route("hello")
        assert result.error is not None

    def test_both_fail_returns_error_result(self):
        """Test 30: Both fail returns error InferenceResult."""
        router = InferenceRouter(mode=PrivacyMode.SMART_ROUTING)
        router.set_local_backend(FailingBackend())
        router.set_cloud_backend(FailingBackend())
        router.set_consent_callback(lambda *_: True)
        result = router.route("hello", task_type="list")
        assert result.error is not None


# ===================================================================
# 31-32. Edge Cases
# ===================================================================

class TestEdgeCases:
    def test_empty_prompt_routes_to_local(self):
        """Test 31: Empty prompt routes to local regardless of mode."""
        router = _router_with_backends(PrivacyMode.PERFORMANCE)
        result = router.route("")
        assert result.backend == "local"

    def test_none_task_type_treated_as_general(self):
        """Test 32: None task_type treated as 'general' (medium complexity)."""
        router = _router_with_backends(PrivacyMode.SMART_ROUTING)
        score = router.score_task("some prompt", None)
        score_general = router.score_task("some prompt", "general")
        assert score == score_general
