"""Tests for the inference interceptor (ring buffer + JSONL log) in LLMService.

Validates that every LLM call is recorded without leaking prompt content,
the ring buffer evicts correctly, and JSONL flushing is resilient.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Ensure project root is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _PROJECT_ROOT)

from core.inference.router import InferenceResult, PrivacyMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_result(backend: str = "local", model: str = "gemma4:e4b",
                 input_tokens: int = 10, output_tokens: int = 20,
                 latency_ms: int = 50) -> InferenceResult:
    return InferenceResult(
        text="response text",
        model=model,
        backend=backend,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )


def _build_service(privacy_mode=PrivacyMode.SMART_ROUTING, budget=None):
    """Build an LLMService with all external deps mocked out."""
    from core.inference.llm import LLMService
    from core.inference.hardware import ModelRecommendation

    with patch("core.inference.llm.HardwareDetector") as MockHW:
        det = MockHW.return_value
        from core.inference.hardware import GPUInfo, HardwareProfile
        det.detect.return_value = HardwareProfile(
            gpu=GPUInfo(vendor="apple", model="M2", vram_gb=16.0),
            ram_gb=16.0, cpu_cores=10, cpu_model="M2", platform="darwin", arch="arm64",
        )
        det.recommend_model.return_value = ModelRecommendation(
            model_name="gemma4:e4b", model_size="4B",
            estimated_ram_gb=4.0, reason="test",
        )
        svc = LLMService(privacy_mode=privacy_mode, budget=budget)

    # Inject mock router so route() returns a controlled result
    mock_router = MagicMock()
    mock_router.route.return_value = _fake_result()
    svc._router = mock_router
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInferenceInterceptor:

    def test_record_created_on_generate(self):
        svc = _build_service()
        svc._flush_inference_record = MagicMock()  # avoid disk I/O
        svc.generate("hello", task_type="general")

        assert len(svc._inference_log) == 1
        rec = svc._inference_log[0]
        assert rec["provider"] == "local"
        assert rec["model"] == "gemma4:e4b"
        assert rec["task_type"] == "general"
        assert rec["input_tokens"] == 10
        assert rec["output_tokens"] == 20
        assert "timestamp" in rec
        assert "cost_usd" in rec
        assert "latency_ms" in rec
        assert rec["privacy_mode"] == "smart_routing"

    def test_no_prompt_in_record(self):
        svc = _build_service()
        svc._flush_inference_record = MagicMock()
        secret_prompt = "top secret prompt with SSN 123-45-6789"
        svc.generate(secret_prompt, task_type="general")

        rec = svc._inference_log[0]
        # No field should contain prompt text
        for value in rec.values():
            if isinstance(value, str):
                assert "top secret" not in value
                assert "SSN" not in value

    def test_ring_buffer_eviction(self):
        svc = _build_service()
        svc._flush_inference_record = MagicMock()
        for i in range(1001):
            svc._router.route.return_value = _fake_result(latency_ms=i)
            svc.generate("p", task_type="general")

        assert len(svc._inference_log) == 1000
        # Oldest record (latency_ms=0) should be evicted; newest (1000) present
        assert svc._inference_log[-1]["latency_ms"] == 1000

    def test_get_inference_log_returns_last_n(self):
        svc = _build_service()
        svc._flush_inference_record = MagicMock()
        for i in range(10):
            svc._router.route.return_value = _fake_result(latency_ms=i)
            svc.generate("p", task_type="general")

        last5 = svc.get_inference_log(last_n=5)
        assert len(last5) == 5
        assert last5[0]["latency_ms"] == 5
        assert last5[-1]["latency_ms"] == 9

    def test_get_inference_stats(self):
        svc = _build_service()
        svc._flush_inference_record = MagicMock()

        # 3 local calls
        for _ in range(3):
            svc._router.route.return_value = _fake_result(backend="local")
            svc.generate("p", task_type="general")
        # 2 cloud calls
        for _ in range(2):
            svc._router.route.return_value = _fake_result(backend="cloud")
            svc.generate("p", task_type="general")

        stats = svc.get_inference_stats()
        assert stats["calls_local"] == 3
        assert stats["calls_cloud"] == 2
        assert stats["total_calls"] == 5
        assert stats["total_latency_ms"] == 250.0  # 5 * 50ms

    def test_flush_writes_jsonl(self, tmp_path):
        svc = _build_service()
        log_file = tmp_path / "inference.jsonl"
        svc._inference_log_path = str(log_file)

        svc.generate("hello", task_type="general")

        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["provider"] == "local"
        assert data["model"] == "gemma4:e4b"

    def test_flush_failure_doesnt_crash(self):
        svc = _build_service()
        # Force _flush to raise by pointing at an unwritable path
        with patch("builtins.open", side_effect=PermissionError("denied")):
            resp = svc.generate("hello", task_type="general")

        # generate still returns successfully
        assert resp.text == "response text"
        # Record still in memory ring buffer
        assert len(svc._inference_log) == 1
