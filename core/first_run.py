"""IntentOS First-Run Wizard.

Guides a new user through initial setup: workspace creation, hardware
detection, credential entry, privacy mode selection, and file-access grants.

All user-facing text uses plain language (no technical jargon).
"""

from __future__ import annotations

import enum
import getpass
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.inference.hardware import HardwareDetector, HardwareProfile, ModelRecommendation
from core.inference.providers import LLMProvider, DEFAULT_MODELS
from core.security.credential_provider import CredentialProvider


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class PrivacyMode(enum.Enum):
    LOCAL_ONLY = "local_only"
    SMART_ROUTING = "smart_routing"
    PERFORMANCE = "performance"


_PRIVACY_LABELS = {
    PrivacyMode.LOCAL_ONLY: "Private (Local Only)",
    PrivacyMode.SMART_ROUTING: "Smart Routing",
    PrivacyMode.PERFORMANCE: "Connected (Performance)",
}


@dataclass
class FirstRunResult:
    hardware_profile: Optional[HardwareProfile] = None
    privacy_mode: PrivacyMode = PrivacyMode.SMART_ROUTING
    model_recommendation: str = ""
    workspace_path: str = ""
    is_complete: bool = False
    llm_provider: Optional[LLMProvider] = None


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

_WORKSPACE_SUBDIRS = ["models", "logs", "cache", "credentials"]


class FirstRunWizard:
    """Orchestrates the IntentOS first-run experience."""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = Path(base_path) if base_path else Path.home() / ".intentos"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def is_first_run(self) -> bool:
        """Return True when settings.json does not yet exist."""
        return not (self.base_path / "settings.json").exists()

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def setup_workspace(self) -> None:
        """Create the full directory structure (idempotent)."""
        print("\n  Setting up your workspace...")
        self.base_path.mkdir(parents=True, exist_ok=True)
        for subdir in _WORKSPACE_SUBDIRS:
            (self.base_path / subdir).mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------

    def detect_hardware(self) -> HardwareProfile:
        """Detect local hardware capabilities."""
        print("  Detecting your hardware...")
        detector = HardwareDetector()
        return detector.detect()

    def recommend_model(self, profile: HardwareProfile) -> str:
        """Return a human-readable model recommendation string."""
        rec: ModelRecommendation = HardwareDetector.recommend_model(profile)
        return rec.model_name

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    _PROVIDER_HELP_URLS = {
        LLMProvider.ANTHROPIC: "https://console.anthropic.com/settings/keys",
        LLMProvider.OPENAI: "https://platform.openai.com/api-keys",
        LLMProvider.GEMINI: "https://aistudio.google.com/app/apikey",
    }

    def select_provider(self, skip_prompts: bool = False) -> LLMProvider:
        """Prompt the user to choose an AI provider."""
        if skip_prompts:
            return LLMProvider.ANTHROPIC

        print("\n  Which AI provider would you like to use?\n")
        print("    [1] Anthropic (Claude)     -- Recommended")
        print("    [2] OpenAI (GPT)")
        print("    [3] Google (Gemini)")
        print("    [4] Custom endpoint         -- Any OpenAI-compatible API")
        print("    [5] None (local only)       -- Requires Ollama installed")
        print()

        choice = input("  Choose [1-5] (default: 1): ").strip()

        mapping = {
            "1": LLMProvider.ANTHROPIC,
            "2": LLMProvider.OPENAI,
            "3": LLMProvider.GEMINI,
            "4": LLMProvider.CUSTOM,
            "5": LLMProvider.OLLAMA,
        }
        return mapping.get(choice, LLMProvider.ANTHROPIC)

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def setup_credentials(
        self,
        skip_prompts: bool = False,
        llm_provider: Optional[LLMProvider] = None,
    ) -> bool:
        """Ensure an API key is available; prompt if needed.

        Returns True if a key is now available.
        """
        provider = CredentialProvider(
            creds_path=self.base_path / "credentials.enc",
            keychain_fallback_path=self.base_path / "master_key.enc",
        )

        chosen = llm_provider or LLMProvider.ANTHROPIC

        # Store provider choice
        provider.store("LLM_PROVIDER", chosen.value)
        provider.store("LLM_MODEL", DEFAULT_MODELS.get(chosen, ""))

        # Ollama needs no API key
        if chosen == LLMProvider.OLLAMA:
            return True

        # Check legacy key for backwards compat
        if chosen == LLMProvider.ANTHROPIC and provider.has("ANTHROPIC_API_KEY"):
            provider.store("LLM_API_KEY", provider.get("ANTHROPIC_API_KEY"))
            return True

        # Already have a key stored
        if provider.has("LLM_API_KEY"):
            return True

        if skip_prompts:
            return False

        help_url = self._PROVIDER_HELP_URLS.get(chosen, "")
        display = chosen.value.capitalize()

        print(f"\n  IntentOS needs your {display} API key.")
        if help_url:
            print(f"  Get one at: {help_url}")

        if chosen == LLMProvider.CUSTOM:
            base_url = input("\n  Enter the endpoint URL: ").strip()
            if base_url:
                provider.store("LLM_BASE_URL", base_url)

        print()
        key = getpass.getpass("  Paste your API key: ").strip()
        if key:
            provider.store("LLM_API_KEY", key)
            # Also store as legacy key for Anthropic
            if chosen == LLMProvider.ANTHROPIC:
                provider.store("ANTHROPIC_API_KEY", key)
            print("  Stored securely.\n")
            return True

        return False

    # ------------------------------------------------------------------
    # Privacy mode
    # ------------------------------------------------------------------

    def select_privacy_mode(self, skip_prompts: bool = False) -> PrivacyMode:
        """Prompt the user to choose a privacy/inference mode."""
        if skip_prompts:
            return PrivacyMode.SMART_ROUTING

        print("\n  How would you like IntentOS to think?\n")
        print("    [1] Private     \u2014 Runs entirely on your device. Works offline.")
        print("    [2] Smart       \u2014 Simple tasks stay local. Complex tasks use your AI account.")
        print("    [3] Connected   \u2014 Uses your AI account for everything. Best quality.")
        print()

        choice = input("  Choose [1/2/3] (default: 2): ").strip()

        mapping = {
            "1": PrivacyMode.LOCAL_ONLY,
            "2": PrivacyMode.SMART_ROUTING,
            "3": PrivacyMode.PERFORMANCE,
        }
        return mapping.get(choice, PrivacyMode.SMART_ROUTING)

    # ------------------------------------------------------------------
    # Grants
    # ------------------------------------------------------------------

    def setup_grants(self) -> None:
        """Write default grants.json with standard user directories."""
        home = str(Path.home())
        grants = {
            "allowed_paths": [
                os.path.join(home, "Documents"),
                os.path.join(home, "Downloads"),
                os.path.join(home, "Desktop"),
            ],
            "denied_paths": [],
        }
        grants_path = self.base_path / "grants.json"
        grants_path.write_text(json.dumps(grants, indent=2))

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    def run(self, skip_prompts: bool = False) -> FirstRunResult:
        """Execute every first-run step and return the collected config."""

        # 1. Workspace
        self.setup_workspace()

        # 2. Hardware
        profile = self.detect_hardware()
        model_name = self.recommend_model(profile)

        # 3. Privacy mode
        privacy = self.select_privacy_mode(skip_prompts=skip_prompts)

        # 4. Provider selection
        chosen_provider = self.select_provider(skip_prompts=skip_prompts)

        # 5. Credentials (with provider context)
        self.setup_credentials(skip_prompts=skip_prompts, llm_provider=chosen_provider)

        # 6. Grants
        self.setup_grants()

        # Build result
        result = FirstRunResult(
            hardware_profile=profile,
            privacy_mode=privacy,
            model_recommendation=model_name,
            workspace_path=str(self.base_path),
            is_complete=True,
            llm_provider=chosen_provider,
        )

        # Persist settings
        settings = {
            "privacy_mode": privacy.value,
            "model": model_name,
            "workspace": str(self.base_path),
            "hardware": profile.to_dict() if profile else None,
            "llm_provider": chosen_provider.value,
        }
        (self.base_path / "settings.json").write_text(json.dumps(settings, indent=2))

        # 6. Welcome
        welcome = self.get_welcome_message(result)
        print(welcome)

        return result

    # ------------------------------------------------------------------
    # Welcome message
    # ------------------------------------------------------------------

    @staticmethod
    def get_welcome_message(result: FirstRunResult) -> str:
        """Return a formatted welcome message."""
        hw = result.hardware_profile
        hw_label = "Unknown hardware"
        if hw:
            hw_label = f"{hw.cpu_model}, {hw.ram_gb:.0f}GB RAM"

        mode_labels = {
            PrivacyMode.LOCAL_ONLY: "Private (Local Only)",
            PrivacyMode.SMART_ROUTING: "Smart Routing",
            PrivacyMode.PERFORMANCE: "Connected (Performance)",
        }
        mode_label = mode_labels.get(result.privacy_mode, str(result.privacy_mode))

        model_suffix = "(local)" if result.privacy_mode == PrivacyMode.LOCAL_ONLY else ""
        model_display = f"{result.model_recommendation} {model_suffix}".strip()

        lines = [
            "",
            "  \u2728 IntentOS is ready.",
            "",
            f"    Hardware:  {hw_label}",
            f"    Model:     {model_display}",
            f"    Mode:      {mode_label}",
            f"    Workspace: {result.workspace_path}",
            "",
            '    Just tell IntentOS what to do.',
            '    Try: "Show me my largest files"',
            "",
        ]
        return "\n".join(lines)
