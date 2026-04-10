"""Tests for OllamaManager — Ollama lifecycle management.

All subprocess and HTTP calls are mocked so tests run without Ollama installed.
"""

from __future__ import annotations

import json
import os
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch, call

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.inference.ollama_manager import (
    OllamaManager,
    OllamaStatus,
    PullProgress,
    OllamaInstallError,
    OllamaConnectionError,
    OllamaModelPullError,
    EMBEDDING_MODEL,
    _parse_pull_progress,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    return OllamaManager()


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class TestDetection:
    @patch("shutil.which", return_value="/usr/local/bin/ollama")
    def test_is_installed_true(self, mock_which):
        assert OllamaManager.is_installed() is True
        mock_which.assert_called_with("ollama")

    @patch("shutil.which", return_value=None)
    def test_is_installed_false(self, mock_which):
        assert OllamaManager.is_installed() is False

    @patch("subprocess.run")
    def test_get_version(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ollama version 0.3.14\n"
        )
        assert OllamaManager.get_version() == "0.3.14"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_get_version_not_installed(self, mock_run):
        assert OllamaManager.get_version() == ""

    @patch("urllib.request.urlopen")
    def test_is_running_true(self, mock_urlopen, manager):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        assert manager.is_running() is True

    @patch("urllib.request.urlopen", side_effect=ConnectionRefusedError)
    def test_is_running_false(self, mock_urlopen, manager):
        assert manager.is_running() is False

    @patch("urllib.request.urlopen")
    def test_list_models(self, mock_urlopen, manager):
        body = json.dumps({
            "models": [
                {"name": "llama3.1:8b"},
                {"name": "nomic-embed-text:latest"},
            ]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        models = manager.list_models()
        assert "llama3.1:8b" in models
        assert "nomic-embed-text:latest" in models

    @patch("urllib.request.urlopen", side_effect=ConnectionRefusedError)
    def test_list_models_offline(self, mock_urlopen, manager):
        assert manager.list_models() == []

    @patch("urllib.request.urlopen")
    def test_has_model_true(self, mock_urlopen, manager):
        body = json.dumps({"models": [{"name": "llama3.1:8b"}]}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert manager.has_model("llama3.1:8b") is True

    @patch("urllib.request.urlopen")
    def test_has_model_false(self, mock_urlopen, manager):
        body = json.dumps({"models": [{"name": "phi3:mini"}]}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert manager.has_model("llama3.1:8b") is False

    @patch.object(OllamaManager, "is_installed", return_value=True)
    @patch.object(OllamaManager, "is_running", return_value=True)
    @patch.object(OllamaManager, "get_version", return_value="0.3.14")
    @patch.object(OllamaManager, "list_models", return_value=["llama3.1:8b"])
    def test_get_status(self, _m1, _m2, _m3, _m4):
        mgr = OllamaManager()
        status = mgr.get_status()
        assert status.installed is True
        assert status.running is True
        assert status.version == "0.3.14"
        assert "llama3.1:8b" in status.models_available


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

class TestInstall:
    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", side_effect=lambda x: "/usr/local/bin/ollama" if x == "brew" else None)
    @patch("subprocess.run")
    def test_install_macos_brew(self, mock_run, mock_which, mock_plat):
        mock_run.return_value = MagicMock(returncode=0)
        # After install, shutil.which("ollama") should find it
        with patch("shutil.which", return_value="/usr/local/bin/ollama"):
            result = OllamaManager._install_macos(silent=True)
        assert result is True

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/ollama")
    def test_install_linux(self, mock_which, mock_run, mock_plat):
        mock_run.return_value = MagicMock(returncode=0)
        result = OllamaManager._install_linux(silent=True)
        assert result is True

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=Exception("network error"))
    def test_install_macos_failure(self, mock_run, mock_which, mock_plat):
        with pytest.raises(OllamaInstallError, match="manually"):
            OllamaManager._install_macos(silent=True)


# ---------------------------------------------------------------------------
# Daemon management
# ---------------------------------------------------------------------------

class TestDaemon:
    @patch.object(OllamaManager, "is_running", return_value=True)
    def test_start_daemon_already_running(self, _mock, manager):
        assert manager.start_daemon() is True

    @patch.object(OllamaManager, "is_installed", return_value=False)
    @patch.object(OllamaManager, "is_running", return_value=False)
    def test_start_daemon_not_installed(self, _m1, _m2):
        mgr = OllamaManager()
        assert mgr.start_daemon() is False

    @patch.object(OllamaManager, "is_installed", return_value=True)
    @patch.object(OllamaManager, "is_running", return_value=True)
    def test_ensure_running_already_up(self, _m1, _m2):
        mgr = OllamaManager()
        assert mgr.ensure_running() is True

    @patch.object(OllamaManager, "is_installed", return_value=False)
    def test_ensure_running_not_installed(self, _mock, manager):
        assert manager.ensure_running() is False


# ---------------------------------------------------------------------------
# Model pulling
# ---------------------------------------------------------------------------

class TestModelPull:
    @patch.object(OllamaManager, "is_running", return_value=False)
    def test_pull_model_not_running(self, _mock, manager):
        with pytest.raises(OllamaConnectionError, match="not running"):
            manager.pull_model("llama3.1:8b")

    @patch.object(OllamaManager, "is_running", return_value=True)
    @patch("urllib.request.urlopen")
    def test_pull_model_success(self, mock_urlopen, _mock_running, manager):
        stream_lines = [
            json.dumps({"status": "pulling manifest"}).encode() + b"\n",
            json.dumps({"status": "downloading abc123", "completed": 500, "total": 1000}).encode() + b"\n",
            json.dumps({"status": "verifying sha256 digest"}).encode() + b"\n",
            json.dumps({"status": "success"}).encode() + b"\n",
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = MagicMock(return_value=iter(stream_lines))
        mock_urlopen.return_value = mock_resp

        progress_updates = []
        result = manager.pull_model("llama3.1:8b", progress_callback=progress_updates.append)

        assert result is True
        assert len(progress_updates) == 4
        assert progress_updates[-1].status == "complete"
        assert progress_updates[-1].percent == 100.0

    @patch.object(OllamaManager, "is_running", return_value=True)
    @patch("urllib.request.urlopen")
    def test_pull_model_error_in_stream(self, mock_urlopen, _mock_running, manager):
        stream_lines = [
            json.dumps({"error": "model not found"}).encode() + b"\n",
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = MagicMock(return_value=iter(stream_lines))
        mock_urlopen.return_value = mock_resp

        with pytest.raises(OllamaModelPullError, match="model not found"):
            manager.pull_model("nonexistent:model")

    @patch.object(OllamaManager, "has_model", return_value=True)
    def test_ensure_model_already_exists(self, _mock, manager):
        progress_updates = []
        result = manager.ensure_model("llama3.1:8b", progress_callback=progress_updates.append)
        assert result is True
        assert len(progress_updates) == 1
        assert progress_updates[0].status == "complete"

    @patch.object(OllamaManager, "has_model", return_value=False)
    @patch.object(OllamaManager, "pull_model", return_value=True)
    def test_ensure_model_needs_pull(self, mock_pull, _mock_has, manager):
        result = manager.ensure_model("llama3.1:8b")
        assert result is True
        mock_pull.assert_called_once()


# ---------------------------------------------------------------------------
# Disk space check
# ---------------------------------------------------------------------------

class TestDiskSpace:
    @patch("shutil.disk_usage")
    def test_sufficient_space(self, mock_usage):
        mock_usage.return_value = MagicMock(free=20 * 1024**3)  # 20GB
        assert OllamaManager.check_disk_space("llama3.1:8b") is None

    @patch("shutil.disk_usage")
    def test_insufficient_space(self, mock_usage):
        mock_usage.return_value = MagicMock(free=1 * 1024**3)  # 1GB
        warning = OllamaManager.check_disk_space("llama3.1:8b")
        assert warning is not None
        assert "free space" in warning


# ---------------------------------------------------------------------------
# Full setup_for_local
# ---------------------------------------------------------------------------

class TestSetupForLocal:
    @patch.object(OllamaManager, "ensure_running", return_value=True)
    @patch.object(OllamaManager, "ensure_model", return_value=True)
    def test_success(self, mock_ensure_model, mock_running, manager):
        result = manager.setup_for_local("llama3.1:8b")
        assert result["success"] is True
        assert "llama3.1:8b" in result["models_pulled"]
        assert EMBEDDING_MODEL in result["models_pulled"]
        assert mock_ensure_model.call_count == 2

    @patch.object(OllamaManager, "ensure_running", return_value=False)
    def test_daemon_not_running(self, _mock, manager):
        result = manager.setup_for_local("llama3.1:8b")
        assert result["success"] is False
        assert len(result["errors"]) > 0

    @patch.object(OllamaManager, "ensure_running", return_value=True)
    @patch.object(OllamaManager, "ensure_model", side_effect=OllamaModelPullError("timeout"))
    def test_pull_failure(self, mock_ensure, mock_running, manager):
        result = manager.setup_for_local("llama3.1:8b")
        assert result["success"] is False
        assert len(result["errors"]) == 2  # both models failed


# ---------------------------------------------------------------------------
# Progress parsing
# ---------------------------------------------------------------------------

class TestProgressParsing:
    def test_downloading(self):
        data = {"status": "downloading abc123", "completed": 500_000_000, "total": 1_000_000_000}
        p = _parse_pull_progress("test:model", data)
        assert p.status == "downloading"
        assert p.percent == 50.0

    def test_verifying(self):
        data = {"status": "verifying sha256 digest"}
        p = _parse_pull_progress("test:model", data)
        assert p.status == "verifying"

    def test_success(self):
        data = {"status": "success"}
        p = _parse_pull_progress("test:model", data)
        assert p.status == "complete"
        assert p.percent == 100.0

    def test_writing_manifest(self):
        data = {"status": "writing manifest"}
        p = _parse_pull_progress("test:model", data)
        assert p.status == "unpacking"

    def test_pulling_manifest(self):
        data = {"status": "pulling manifest"}
        p = _parse_pull_progress("test:model", data)
        assert p.status == "downloading"
