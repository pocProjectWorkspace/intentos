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
    # Credentials
    # ------------------------------------------------------------------

    def setup_credentials(self, skip_prompts: bool = False) -> bool:
        """Ensure an API key is available; prompt if needed.

        Returns True if a key is now available.
        """
        provider = CredentialProvider(
            creds_path=self.base_path / "credentials.enc",
            keychain_fallback_path=self.base_path / "master_key.enc",
        )

        if provider.has("ANTHROPIC_API_KEY"):
            return True

        if skip_prompts:
            return False

        print("\n  IntentOS needs your Anthropic API key.")
        print("  Get one at: https://console.anthropic.com/settings/keys\n")

        key = getpass.getpass("  Paste your API key: ").strip()
        if key:
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

        # 3. Credentials
        self.setup_credentials(skip_prompts=skip_prompts)

        # 4. Privacy mode
        privacy = self.select_privacy_mode(skip_prompts=skip_prompts)

        # 5. Grants
        self.setup_grants()

        # Build result
        result = FirstRunResult(
            hardware_profile=profile,
            privacy_mode=privacy,
            model_recommendation=model_name,
            workspace_path=str(self.base_path),
            is_complete=True,
        )

        # Persist settings
        settings = {
            "privacy_mode": privacy.value,
            "model": model_name,
            "workspace": str(self.base_path),
            "hardware": profile.to_dict() if profile else None,
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
