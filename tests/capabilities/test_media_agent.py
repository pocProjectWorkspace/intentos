"""
Tests for the IntentOS Media Agent (Phase 2C.4).

All tests work WITHOUT ffmpeg installed by testing:
- ACP contract (input/output structure)
- Path validation
- Dry run behavior
- Parameter validation
- Error handling for missing ffmpeg
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from capabilities.media_agent.agent import run, SUPPORTED_FORMATS, _check_ffmpeg, _check_ffprobe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(tmp_path: str, workspace: str | None = None) -> dict:
    """Build a minimal ACP context dict."""
    ws = workspace or os.path.join(tmp_path, "workspace")
    os.makedirs(os.path.join(ws, "outputs"), exist_ok=True)
    return {
        "granted_paths": [tmp_path],
        "workspace": ws,
        "task_id": "test-001",
    }


def _make_input(action: str, params: dict | None = None, context: dict | None = None) -> dict:
    return {
        "action": action,
        "params": params or {},
        "context": context or {},
    }


# ===================================================================
# ACP Contract
# ===================================================================

class TestACPContract:
    """1-3: run() returns correct structure."""

    def test_run_returns_required_keys(self, tmp_path):
        """1. run() returns dict with status, action_performed, result, metadata."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("get_info", {"path": str(tmp_path / "fake.mp4")}, ctx)
        out = run(inp)
        assert isinstance(out, dict)
        assert "status" in out
        assert "action_performed" in out
        assert "result" in out
        assert "metadata" in out

    def test_unknown_action_returns_error(self, tmp_path):
        """2. Unknown action returns status='error', code='UNKNOWN_ACTION'."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("fly_to_mars", {}, ctx)
        out = run(inp)
        assert out["status"] == "error"
        assert out["error"]["code"] == "UNKNOWN_ACTION"

    def test_metadata_always_present(self, tmp_path):
        """3. metadata always present with required fields."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("get_info", {"path": str(tmp_path / "fake.mp4")}, ctx)
        out = run(inp)
        meta = out["metadata"]
        assert "duration_ms" in meta
        assert "paths_accessed" in meta


# ===================================================================
# get_info action
# ===================================================================

class TestGetInfo:
    """4-6: get_info action tests."""

    @patch("capabilities.media_agent.agent._check_ffprobe", return_value=False)
    def test_ffprobe_not_installed(self, mock_probe, tmp_path):
        """4. Missing ffprobe returns plain language error."""
        ctx = _make_context(str(tmp_path))
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("get_info", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "error"
        assert "not installed" in out["error"]["message"].lower() or \
               "media tools" in out["error"]["message"].lower()

    def test_dry_run(self, tmp_path):
        """5. Dry run returns what would happen."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("get_info", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        assert "dry_run" in out["metadata"] or out["metadata"].get("dry_run") is True

    def test_missing_file(self, tmp_path):
        """6. Missing file returns error."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("get_info", {"path": str(tmp_path / "nonexistent.mp4")}, ctx)
        out = run(inp)
        assert out["status"] == "error"


# ===================================================================
# convert action
# ===================================================================

class TestConvert:
    """7-12: convert action tests."""

    def test_requires_source_and_format(self, tmp_path):
        """7. Parameter validation: requires source path and target_format."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("convert", {"path": str(tmp_path / "v.mp4")}, ctx)
        out = run(inp)
        assert out["status"] == "error"

    def test_missing_source_path(self, tmp_path):
        """8. Missing source path returns error."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("convert", {"target_format": "mkv"}, ctx)
        out = run(inp)
        assert out["status"] == "error"

    def test_unsupported_format(self, tmp_path):
        """9. Unsupported format returns error with list of supported formats."""
        ctx = _make_context(str(tmp_path))
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("convert", {"path": str(src), "target_format": "xyz"}, ctx)
        out = run(inp)
        assert out["status"] == "error"
        # Error message should list supported formats
        msg = out["error"]["message"].lower()
        assert "supported" in msg or "format" in msg

    def test_dry_run(self, tmp_path):
        """10. Dry run describes the conversion."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("convert", {"path": str(src), "target_format": "mkv"}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        assert out["metadata"].get("dry_run") is True
        # Result should describe what would happen
        assert "mkv" in str(out["result"]).lower()

    def test_path_outside_granted(self, tmp_path):
        """11. Path outside granted_paths returns error."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("convert", {"path": "/etc/passwd", "target_format": "mkv"}, ctx)
        out = run(inp)
        assert out["status"] == "error"
        assert "path" in out["error"]["message"].lower() or \
               "permission" in out["error"]["message"].lower() or \
               "granted" in out["error"]["message"].lower() or \
               "outside" in out["error"]["message"].lower()

    def test_output_goes_to_workspace_outputs(self, tmp_path):
        """12. Output goes to workspace/outputs/."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("convert", {"path": str(src), "target_format": "mkv"}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        result_str = str(out["result"])
        assert "outputs" in result_str


# ===================================================================
# trim action
# ===================================================================

class TestTrim:
    """13-16: trim action tests."""

    def test_requires_time_params(self, tmp_path):
        """13. Requires start_time and/or end_time."""
        ctx = _make_context(str(tmp_path))
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("trim", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "error"

    def test_missing_both_times(self, tmp_path):
        """14. Missing both start_time and end_time returns error."""
        ctx = _make_context(str(tmp_path))
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("trim", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "error"
        msg = out["error"]["message"].lower()
        assert "start" in msg or "time" in msg

    def test_invalid_time_format(self, tmp_path):
        """15. Invalid time format returns error."""
        ctx = _make_context(str(tmp_path))
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("trim", {"path": str(src), "start_time": "abc"}, ctx)
        out = run(inp)
        assert out["status"] == "error"

    def test_dry_run(self, tmp_path):
        """16. Dry run describes the trim."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("trim", {"path": str(src), "start_time": "00:01:00", "end_time": "00:02:00"}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        assert out["metadata"].get("dry_run") is True


# ===================================================================
# extract_audio action
# ===================================================================

class TestExtractAudio:
    """17-19: extract_audio action tests."""

    def test_requires_source_path(self, tmp_path):
        """17. Requires source video path."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("extract_audio", {}, ctx)
        out = run(inp)
        assert out["status"] == "error"

    def test_dry_run(self, tmp_path):
        """18. Dry run describes extraction."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("extract_audio", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        assert out["metadata"].get("dry_run") is True

    def test_path_validation(self, tmp_path):
        """19. Path validation enforced."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("extract_audio", {"path": "/etc/passwd"}, ctx)
        out = run(inp)
        assert out["status"] == "error"


# ===================================================================
# compress action
# ===================================================================

class TestCompress:
    """20-22: compress action tests."""

    def test_requires_source_path(self, tmp_path):
        """20. Requires source path."""
        ctx = _make_context(str(tmp_path))
        inp = _make_input("compress", {}, ctx)
        out = run(inp)
        assert out["status"] == "error"

    def test_quality_parameter(self, tmp_path):
        """21. Quality parameter (low/medium/high, default medium)."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        # Default quality
        inp = _make_input("compress", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        assert "medium" in str(out["result"]).lower()

        # Explicit quality
        inp2 = _make_input("compress", {"path": str(src), "quality": "high"}, ctx)
        out2 = run(inp2)
        assert out2["status"] == "success"
        assert "high" in str(out2["result"]).lower()

    def test_dry_run(self, tmp_path):
        """22. Dry run describes compression."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        inp = _make_input("compress", {"path": str(src)}, ctx)
        out = run(inp)
        assert out["status"] == "success"
        assert out["metadata"].get("dry_run") is True


# ===================================================================
# Utility
# ===================================================================

class TestUtility:
    """23-25: Utility function tests."""

    def test_check_ffmpeg_returns_bool(self):
        """23. _check_ffmpeg() returns bool."""
        result = _check_ffmpeg()
        assert isinstance(result, bool)

    def test_check_ffprobe_returns_bool(self):
        """24. _check_ffprobe() returns bool."""
        result = _check_ffprobe()
        assert isinstance(result, bool)

    def test_supported_formats(self):
        """25. Supported formats list contains expected entries."""
        expected = {"mp4", "mkv", "avi", "mov", "mp3", "wav", "flac", "aac", "ogg", "webm"}
        assert expected == SUPPORTED_FORMATS


# ===================================================================
# Path Enforcement
# ===================================================================

class TestPathEnforcement:
    """26-27: Path enforcement tests."""

    def test_rejects_paths_outside_granted(self, tmp_path):
        """26. Rejects paths outside granted_paths."""
        ctx = _make_context(str(tmp_path))
        for action in ["get_info", "convert", "trim", "extract_audio", "compress"]:
            params = {"path": "/root/evil.mp4"}
            if action == "convert":
                params["target_format"] = "mkv"
            if action == "trim":
                params["start_time"] = "00:00:01"
            inp = _make_input(action, params, ctx)
            out = run(inp)
            assert out["status"] == "error", f"{action} should reject path outside granted_paths"

    def test_writes_to_workspace_outputs(self, tmp_path):
        """27. Writes to workspace/outputs/."""
        ctx = _make_context(str(tmp_path))
        ctx["dry_run"] = True
        src = tmp_path / "video.mp4"
        src.touch()
        for action in ["convert", "trim", "extract_audio", "compress"]:
            params = {"path": str(src)}
            if action == "convert":
                params["target_format"] = "mkv"
            if action == "trim":
                params["start_time"] = "00:00:01"
            inp = _make_input(action, params, ctx)
            out = run(inp)
            assert out["status"] == "success", f"{action} dry run should succeed"
            result_str = str(out["result"])
            assert "outputs" in result_str, f"{action} output should reference outputs dir"
