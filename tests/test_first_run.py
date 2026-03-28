"""Tests for the IntentOS First-Run Wizard (core/first_run.py).

TDD: These tests are written BEFORE the implementation.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from core.first_run import FirstRunWizard, FirstRunResult, PrivacyMode
from core.inference.hardware import HardwareProfile, GPUInfo, ModelRecommendation
from core.inference.providers import LLMProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_base(tmp_path):
    """Provide a temporary base path for ~/.intentos equivalent."""
    return tmp_path / ".intentos"


@pytest.fixture
def wizard(tmp_base):
    """Wizard instance using a temp base path."""
    return FirstRunWizard(base_path=tmp_base)


@pytest.fixture
def mock_hardware_profile():
    """A typical Apple-Silicon hardware profile."""
    return HardwareProfile(
        gpu=GPUInfo(vendor="apple", model="Apple M1", vram_gb=16.0),
        ram_gb=16.0,
        cpu_cores=8,
        cpu_model="Apple M1",
        platform="darwin",
        arch="arm64",
    )


# ---------------------------------------------------------------------------
# 1-2  Detection: is_first_run
# ---------------------------------------------------------------------------

class TestIsFirstRun:
    def test_returns_true_when_settings_missing(self, wizard, tmp_base):
        """Test 1: is_first_run returns True if settings.json doesn't exist."""
        assert wizard.is_first_run() is True

    def test_returns_false_when_settings_exist(self, wizard, tmp_base):
        """Test 2: is_first_run returns False if settings.json exists."""
        tmp_base.mkdir(parents=True, exist_ok=True)
        (tmp_base / "settings.json").write_text("{}")
        assert wizard.is_first_run() is False


# ---------------------------------------------------------------------------
# 3-4  Workspace Setup
# ---------------------------------------------------------------------------

class TestSetupWorkspace:
    def test_creates_directory_structure(self, wizard, tmp_base):
        """Test 3: setup_workspace creates full directory structure."""
        wizard.setup_workspace()
        assert tmp_base.exists()
        assert (tmp_base / "models").is_dir()
        assert (tmp_base / "logs").is_dir()
        assert (tmp_base / "cache").is_dir()
        assert (tmp_base / "credentials").is_dir()

    def test_idempotent(self, wizard, tmp_base):
        """Test 4: setup_workspace is idempotent — calling twice doesn't error."""
        wizard.setup_workspace()
        wizard.setup_workspace()  # should not raise
        assert tmp_base.exists()


# ---------------------------------------------------------------------------
# 5-6  Hardware Detection
# ---------------------------------------------------------------------------

class TestDetectHardware:
    @patch("core.first_run.HardwareDetector")
    def test_returns_hardware_profile(self, MockDetector, wizard, mock_hardware_profile):
        """Test 5: detect_hardware returns HardwareProfile with GPU, RAM, CPU."""
        mock_instance = MockDetector.return_value
        mock_instance.detect.return_value = mock_hardware_profile

        profile = wizard.detect_hardware()
        assert isinstance(profile, HardwareProfile)
        assert profile.gpu is not None
        assert profile.ram_gb == 16.0
        assert profile.cpu_cores == 8

    @patch("core.first_run.HardwareDetector")
    def test_recommend_model_returns_string(self, MockDetector, wizard, mock_hardware_profile):
        """Test 6: recommend_model returns a model recommendation string."""
        mock_instance = MockDetector.return_value
        mock_instance.detect.return_value = mock_hardware_profile
        MockDetector.recommend_model.return_value = ModelRecommendation(
            model_name="llama3.1:8b",
            model_size="8B",
            estimated_ram_gb=6.0,
            reason="Good for 16GB RAM with GPU.",
        )

        rec = wizard.recommend_model(mock_hardware_profile)
        assert isinstance(rec, str)
        assert len(rec) > 0


# ---------------------------------------------------------------------------
# 7-9  Credential Setup
# ---------------------------------------------------------------------------

class TestSetupCredentials:
    @patch("core.first_run.CredentialProvider")
    @patch("getpass.getpass", return_value="sk-ant-fake-key-123")
    def test_prompts_for_key_if_not_stored(self, mock_getpass, MockProvider, wizard):
        """Test 7: setup_credentials prompts for API key if not stored."""
        provider = MockProvider.return_value
        provider.has.return_value = False

        wizard.setup_credentials(skip_prompts=False)
        provider.has.assert_called()
        provider.store.assert_called()

    @patch("core.first_run.CredentialProvider")
    def test_skips_prompt_if_key_exists(self, MockProvider, wizard):
        """Test 8: setup_credentials skips prompt if key already exists."""
        provider = MockProvider.return_value
        provider.has.return_value = True
        provider.get.return_value = "sk-ant-existing-key"

        wizard.setup_credentials(skip_prompts=False)
        # Should store provider config but not prompt for a new key
        # (getpass should not be called)
        store_calls = provider.store.call_args_list
        key_names = [c[0][0] for c in store_calls]
        assert "LLM_PROVIDER" in key_names
        assert "LLM_MODEL" in key_names

    @patch("core.first_run.CredentialProvider")
    @patch("getpass.getpass", return_value="sk-ant-fake-key-456")
    def test_stores_via_credential_provider(self, mock_getpass, MockProvider, wizard):
        """Test 9: Stores credential securely via CredentialProvider."""
        provider = MockProvider.return_value
        provider.has.return_value = False

        wizard.setup_credentials(skip_prompts=False)
        store_calls = provider.store.call_args_list
        stored = {c[0][0]: c[0][1] for c in store_calls}
        assert stored["LLM_API_KEY"] == "sk-ant-fake-key-456"
        assert stored["ANTHROPIC_API_KEY"] == "sk-ant-fake-key-456"


# ---------------------------------------------------------------------------
# 10-13  Privacy Mode Selection
# ---------------------------------------------------------------------------

class TestSelectPrivacyMode:
    @patch("builtins.input", return_value="1")
    def test_input_1_returns_local_only(self, mock_input, wizard):
        """Test 10: Input '1' selects LOCAL_ONLY."""
        mode = wizard.select_privacy_mode(skip_prompts=False)
        assert mode == PrivacyMode.LOCAL_ONLY

    @patch("builtins.input", return_value="2")
    def test_input_2_returns_smart_routing(self, mock_input, wizard):
        """Test 11: Input '2' selects SMART_ROUTING."""
        mode = wizard.select_privacy_mode(skip_prompts=False)
        assert mode == PrivacyMode.SMART_ROUTING

    @patch("builtins.input", return_value="3")
    def test_input_3_returns_performance(self, mock_input, wizard):
        """Test 12: Input '3' selects PERFORMANCE."""
        mode = wizard.select_privacy_mode(skip_prompts=False)
        assert mode == PrivacyMode.PERFORMANCE

    @patch("builtins.input", return_value="banana")
    def test_invalid_defaults_to_smart_routing(self, mock_input, wizard):
        """Test 13: Invalid input defaults to SMART_ROUTING."""
        mode = wizard.select_privacy_mode(skip_prompts=False)
        assert mode == PrivacyMode.SMART_ROUTING


# ---------------------------------------------------------------------------
# 14-15  Grants Setup
# ---------------------------------------------------------------------------

class TestSetupGrants:
    def test_creates_grants_json(self, wizard, tmp_base):
        """Test 14: setup_grants creates default grants.json."""
        wizard.setup_workspace()
        wizard.setup_grants()
        grants_path = tmp_base / "grants.json"
        assert grants_path.exists()
        data = json.loads(grants_path.read_text())
        assert "allowed_paths" in data

    def test_default_grants_include_standard_dirs(self, wizard, tmp_base):
        """Test 15: Default grants include ~/Documents, ~/Downloads, ~/Desktop."""
        wizard.setup_workspace()
        wizard.setup_grants()
        data = json.loads((tmp_base / "grants.json").read_text())
        paths = data["allowed_paths"]
        home = str(Path.home())
        assert os.path.join(home, "Documents") in paths
        assert os.path.join(home, "Downloads") in paths
        assert os.path.join(home, "Desktop") in paths


# ---------------------------------------------------------------------------
# 16-18  Full Wizard run()
# ---------------------------------------------------------------------------

class TestFullWizardRun:
    @patch("core.first_run.CredentialProvider")
    @patch("core.first_run.HardwareDetector")
    @patch("builtins.input", return_value="2")
    @patch("getpass.getpass", return_value="sk-ant-fake-key")
    def test_run_executes_all_steps(self, mock_gp, mock_input, MockDetector, MockProvider, wizard, tmp_base, mock_hardware_profile):
        """Test 16: run() executes all steps in order."""
        mock_det = MockDetector.return_value
        mock_det.detect.return_value = mock_hardware_profile
        MockDetector.recommend_model.return_value = ModelRecommendation(
            model_name="llama3.1:8b", model_size="8B",
            estimated_ram_gb=6.0, reason="Good fit.",
        )
        prov = MockProvider.return_value
        prov.has.return_value = False

        result = wizard.run(skip_prompts=False)

        # Workspace was created
        assert tmp_base.exists()
        # Grants were created
        assert (tmp_base / "grants.json").exists()
        # Settings were written
        assert (tmp_base / "settings.json").exists()
        assert isinstance(result, FirstRunResult)

    @patch("core.first_run.CredentialProvider")
    @patch("core.first_run.HardwareDetector")
    @patch("builtins.input", return_value="1")
    @patch("getpass.getpass", return_value="sk-ant-fake-key")
    def test_run_returns_first_run_result(self, mock_gp, mock_input, MockDetector, MockProvider, wizard, tmp_base, mock_hardware_profile):
        """Test 17: run() returns FirstRunResult with all collected config."""
        mock_det = MockDetector.return_value
        mock_det.detect.return_value = mock_hardware_profile
        MockDetector.recommend_model.return_value = ModelRecommendation(
            model_name="llama3.1:8b", model_size="8B",
            estimated_ram_gb=6.0, reason="Good fit.",
        )
        prov = MockProvider.return_value
        prov.has.return_value = False

        result = wizard.run(skip_prompts=False)
        assert result.is_complete is True
        assert result.privacy_mode == PrivacyMode.LOCAL_ONLY
        assert result.model_recommendation == "llama3.1:8b"
        assert result.workspace_path == str(tmp_base)

    @patch("core.first_run.CredentialProvider")
    @patch("core.first_run.HardwareDetector")
    @patch("builtins.input", return_value="2")
    @patch("getpass.getpass", return_value="sk-ant-fake-key")
    def test_first_run_result_fields(self, mock_gp, mock_input, MockDetector, MockProvider, wizard, tmp_base, mock_hardware_profile):
        """Test 18: FirstRunResult has all required fields."""
        mock_det = MockDetector.return_value
        mock_det.detect.return_value = mock_hardware_profile
        MockDetector.recommend_model.return_value = ModelRecommendation(
            model_name="llama3.1:8b", model_size="8B",
            estimated_ram_gb=6.0, reason="Good fit.",
        )
        prov = MockProvider.return_value
        prov.has.return_value = False

        result = wizard.run(skip_prompts=False)
        assert hasattr(result, "hardware_profile")
        assert hasattr(result, "privacy_mode")
        assert hasattr(result, "model_recommendation")
        assert hasattr(result, "workspace_path")
        assert hasattr(result, "is_complete")


# ---------------------------------------------------------------------------
# 19-21  Welcome Message
# ---------------------------------------------------------------------------

class TestWelcomeMessage:
    def test_get_welcome_message_returns_text(self, wizard, mock_hardware_profile):
        """Test 19: get_welcome_message returns formatted welcome text."""
        result = FirstRunResult(
            hardware_profile=mock_hardware_profile,
            privacy_mode=PrivacyMode.SMART_ROUTING,
            model_recommendation="llama3.1:8b",
            workspace_path="/tmp/.intentos",
            is_complete=True,
        )
        msg = wizard.get_welcome_message(result)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_welcome_includes_hardware_model_privacy_path(self, wizard, mock_hardware_profile):
        """Test 20: Welcome includes detected hardware, model, privacy mode, workspace."""
        result = FirstRunResult(
            hardware_profile=mock_hardware_profile,
            privacy_mode=PrivacyMode.SMART_ROUTING,
            model_recommendation="llama3.1:8b",
            workspace_path="/tmp/.intentos",
            is_complete=True,
        )
        msg = wizard.get_welcome_message(result)
        assert "Apple M1" in msg
        assert "llama3.1:8b" in msg
        assert "Smart" in msg
        assert "/tmp/.intentos" in msg

    def test_welcome_includes_first_task_suggestion(self, wizard, mock_hardware_profile):
        """Test 21: Welcome includes first task suggestion."""
        result = FirstRunResult(
            hardware_profile=mock_hardware_profile,
            privacy_mode=PrivacyMode.SMART_ROUTING,
            model_recommendation="llama3.1:8b",
            workspace_path="/tmp/.intentos",
            is_complete=True,
        )
        msg = wizard.get_welcome_message(result)
        assert "Show me my largest files" in msg


# ---------------------------------------------------------------------------
# 22  Skip Mode
# ---------------------------------------------------------------------------

class TestSkipMode:
    @patch("core.first_run.CredentialProvider")
    @patch("core.first_run.HardwareDetector")
    def test_skip_prompts_uses_defaults(self, MockDetector, MockProvider, wizard, tmp_base, mock_hardware_profile):
        """Test 22: run(skip_prompts=True) uses all defaults without user interaction."""
        mock_det = MockDetector.return_value
        mock_det.detect.return_value = mock_hardware_profile
        MockDetector.recommend_model.return_value = ModelRecommendation(
            model_name="llama3.1:8b", model_size="8B",
            estimated_ram_gb=6.0, reason="Good fit.",
        )
        prov = MockProvider.return_value
        prov.has.return_value = True  # key already exists

        # No input/getpass patching — should not prompt
        result = wizard.run(skip_prompts=True)
        assert result.is_complete is True
        assert result.privacy_mode == PrivacyMode.SMART_ROUTING  # default
        assert result.model_recommendation == "llama3.1:8b"


# ---------------------------------------------------------------------------
# 23-28  Provider Selection
# ---------------------------------------------------------------------------

class TestSelectProvider:
    @patch("builtins.input", return_value="1")
    def test_input_1_returns_anthropic(self, mock_input, wizard):
        """Test 23: Input '1' selects ANTHROPIC."""
        provider = wizard.select_provider(skip_prompts=False)
        assert provider == LLMProvider.ANTHROPIC

    @patch("builtins.input", return_value="2")
    def test_input_2_returns_openai(self, mock_input, wizard):
        """Test 24: Input '2' selects OPENAI."""
        provider = wizard.select_provider(skip_prompts=False)
        assert provider == LLMProvider.OPENAI

    @patch("builtins.input", return_value="3")
    def test_input_3_returns_gemini(self, mock_input, wizard):
        """Test 25: Input '3' selects GEMINI."""
        provider = wizard.select_provider(skip_prompts=False)
        assert provider == LLMProvider.GEMINI

    @patch("builtins.input", return_value="4")
    def test_input_4_returns_custom(self, mock_input, wizard):
        """Test 26: Input '4' selects CUSTOM."""
        provider = wizard.select_provider(skip_prompts=False)
        assert provider == LLMProvider.CUSTOM

    @patch("builtins.input", return_value="5")
    def test_input_5_returns_ollama(self, mock_input, wizard):
        """Test 27: Input '5' selects OLLAMA."""
        provider = wizard.select_provider(skip_prompts=False)
        assert provider == LLMProvider.OLLAMA

    @patch("builtins.input", return_value="banana")
    def test_invalid_defaults_to_anthropic(self, mock_input, wizard):
        """Test 28: Invalid input defaults to ANTHROPIC."""
        provider = wizard.select_provider(skip_prompts=False)
        assert provider == LLMProvider.ANTHROPIC

    def test_skip_prompts_returns_anthropic(self, wizard):
        """Test 29: skip_prompts=True returns ANTHROPIC."""
        provider = wizard.select_provider(skip_prompts=True)
        assert provider == LLMProvider.ANTHROPIC
