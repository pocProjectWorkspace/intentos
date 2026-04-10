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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from core.inference.hardware import HardwareDetector, HardwareProfile, ModelRecommendation
from core.inference.providers import LLMProvider, DEFAULT_MODELS
from core.inference.ollama_manager import (
    OllamaManager,
    OllamaStatus,
    PullProgress,
    OllamaInstallError,
    OllamaConnectionError,
    OllamaModelPullError,
    EMBEDDING_MODEL,
)
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
    ollama_status: Optional[OllamaStatus] = None
    models_pulled: List[str] = field(default_factory=list)


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
        """Prompt the user to choose a privacy/inference mode.

        Default is Private (LOCAL_ONLY) per FIRST_LAUNCH.md.
        """
        if skip_prompts:
            return PrivacyMode.LOCAL_ONLY

        print("\n  How would you like IntentOS to think?\n")
        print("    [1] Private     \u2014 Runs entirely on your device. Works offline.")
        print("                      Nothing leaves your computer. Ever.")
        print("                      One-time setup: ~2 GB download\n")
        print("    [2] Connected   \u2014 Uses your AI account for everything.")
        print("                      No download needed. Requires internet.\n")
        print("    [3] Smart       \u2014 Simple tasks stay local.")
        print("                      Complex tasks use your AI account.\n")

        choice = input("  Choose [1/2/3] (default: 1): ").strip()

        mapping = {
            "1": PrivacyMode.LOCAL_ONLY,
            "2": PrivacyMode.PERFORMANCE,
            "3": PrivacyMode.SMART_ROUTING,
        }
        return mapping.get(choice, PrivacyMode.LOCAL_ONLY)

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
    # Ollama setup (Screen 3A)
    # ------------------------------------------------------------------

    def setup_ollama(
        self,
        hardware_profile: HardwareProfile,
        model_name: str,
        skip_prompts: bool = False,
    ) -> tuple:
        """Install Ollama if needed, pull recommended model + embeddings.

        Returns (success: bool, models_pulled: list[str]).
        """
        manager = OllamaManager()

        # Check disk space
        warning = manager.check_disk_space(model_name)
        if warning:
            print(f"\n  {warning}")
            if not skip_prompts:
                proceed = input("  Continue anyway? [y/N]: ").strip()
                if not proceed or proceed.lower() != "y":
                    return (False, [])

        # Install if needed
        if not manager.is_installed():
            if not skip_prompts:
                print("\n  IntentOS needs a small engine to run AI on your device.")
                print("  This is a one-time install (~100 MB).\n")
                proceed = input("  Install now? [Y/n]: ").strip()
                if proceed.lower() == "n":
                    return (False, [])

            print("  Installing local AI engine...")
            try:
                manager.install(silent=True)
                print("  [ok] Installed\n")
            except OllamaInstallError as exc:
                print(f"\n  {exc}\n")
                return (False, [])
        else:
            print("  [ok] Local AI engine found\n")

        # Setup header
        print("  Setting up your thinking engine\n")
        print("  This happens once and takes a few minutes.")
        print("  After this, IntentOS works instantly \u2014 even")
        print("  without an internet connection.\n")

        # Pull models
        result = manager.setup_for_local(
            model_name,
            progress_callback=self._print_pull_progress,
        )
        print()  # newline after progress

        if result["success"]:
            pulled = result["models_pulled"]
            print(f"  [ok] {len(pulled)} component(s) ready\n")
            return (True, pulled)
        else:
            for err in result["errors"]:
                print(f"  [!!] {err}")
            print()
            return (False, result.get("models_pulled", []))

    @staticmethod
    def _print_pull_progress(progress: PullProgress) -> None:
        """Format and print model pull progress."""
        # Map status to plain-language labels
        labels = {
            "downloading": "Downloading your local AI...",
            "unpacking": "Almost there \u2014 unpacking...",
            "verifying": "Running a quick check...",
            "complete": "Ready!",
        }
        # Switch label when pulling embedding model
        if progress.model == EMBEDDING_MODEL:
            labels["downloading"] = "Setting up your search engine..."

        label = labels.get(progress.status, progress.status)

        if progress.status == "complete":
            print(f"  [ok] {progress.model}")
        elif progress.total_gb > 0:
            bar_width = 22
            filled = int(bar_width * progress.percent / 100)
            bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
            print(f"\r  [{bar}] {progress.percent:5.1f}%  {label}", end="", flush=True)
        else:
            print(f"\r  {label}", end="", flush=True)

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    def run(self, skip_prompts: bool = False) -> FirstRunResult:
        """Execute every first-run step and return the collected config.

        Flow matches FIRST_LAUNCH.md:
          Screen 1: Welcome (caller handles this)
          Screen 2: The ONE Choice (privacy mode)
          Screen 3A: Local setup (Ollama install + model pull)
          Screen 3B: Cloud setup (provider + API key)
          Screen 4: Ready
        """

        # 1. Workspace
        self.setup_workspace()

        # 2. Hardware detection (silent)
        profile = self.detect_hardware()
        model_name = self.recommend_model(profile)

        # 3. Screen 2: The ONE Choice
        privacy = self.select_privacy_mode(skip_prompts=skip_prompts)

        # 4. Branch based on choice
        ollama_status = None
        models_pulled: list = []
        chosen_provider = LLMProvider.OLLAMA  # default

        needs_local = privacy in (PrivacyMode.LOCAL_ONLY, PrivacyMode.SMART_ROUTING)
        needs_cloud = privacy in (PrivacyMode.PERFORMANCE, PrivacyMode.SMART_ROUTING)

        # Screen 3A: Local setup (if Private or Smart)
        if needs_local:
            success, models_pulled = self.setup_ollama(
                hardware_profile=profile,
                model_name=model_name,
                skip_prompts=skip_prompts,
            )
            manager = OllamaManager()
            ollama_status = manager.get_status()

            if not success and privacy == PrivacyMode.LOCAL_ONLY:
                # Offer fallback to Connected mode
                if not skip_prompts:
                    print("  The download did not complete \u2014 probably a network hiccup.\n")
                    fallback = input("  [1] Try again  [2] Use connected mode instead: ").strip()
                    if fallback == "2":
                        privacy = PrivacyMode.PERFORMANCE
                        needs_cloud = True
                    else:
                        success, models_pulled = self.setup_ollama(
                            hardware_profile=profile,
                            model_name=model_name,
                            skip_prompts=skip_prompts,
                        )

        # Screen 3B: Cloud setup (if Connected or Smart)
        if needs_cloud:
            chosen_provider = self.select_provider(skip_prompts=skip_prompts)
            self.setup_credentials(skip_prompts=skip_prompts, llm_provider=chosen_provider)
        elif privacy == PrivacyMode.LOCAL_ONLY:
            chosen_provider = LLMProvider.OLLAMA
            self.setup_credentials(skip_prompts=True, llm_provider=LLMProvider.OLLAMA)

        # 5. Grants
        self.setup_grants()

        # Build result
        result = FirstRunResult(
            hardware_profile=profile,
            privacy_mode=privacy,
            model_recommendation=model_name,
            workspace_path=str(self.base_path),
            is_complete=True,
            llm_provider=chosen_provider,
            ollama_status=ollama_status,
            models_pulled=models_pulled,
        )

        # Persist settings
        settings = {
            "privacy_mode": privacy.value,
            "model": model_name,
            "workspace": str(self.base_path),
            "hardware": profile.to_dict() if profile else None,
            "llm_provider": chosen_provider.value,
            "ollama_models": models_pulled,
            "embedding_model": EMBEDDING_MODEL if EMBEDDING_MODEL in models_pulled else "",
        }
        (self.base_path / "settings.json").write_text(json.dumps(settings, indent=2))

        # Screen 4: Ready
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
            PrivacyMode.LOCAL_ONLY: "Private \u2014 everything runs on your device",
            PrivacyMode.SMART_ROUTING: "Smart \u2014 simple tasks local, complex tasks online",
            PrivacyMode.PERFORMANCE: "Connected \u2014 using your AI account",
        }
        mode_label = mode_labels.get(result.privacy_mode, str(result.privacy_mode))

        model_suffix = "(on device)" if result.privacy_mode == PrivacyMode.LOCAL_ONLY else ""
        model_display = f"{result.model_recommendation} {model_suffix}".strip()

        lines = [
            "",
            "  IntentOS is ready.",
            "",
            f"    Hardware:  {hw_label}",
            f"    AI:        {model_display}",
            f"    Mode:      {mode_label}",
        ]
        if result.models_pulled:
            lines.append(f"    Ready:     {len(result.models_pulled)} component(s) installed")
        lines += [
            "",
            '    Just tell IntentOS what to do.',
            '    Try: "Show me my largest files"',
            "",
        ]
        return "\n".join(lines)
