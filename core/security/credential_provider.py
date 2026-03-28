"""
IntentOS Credential Provider

Single entry point for retrieving API keys and secrets.
Priority order:
  1. Encrypted credential store (secure, recommended)
  2. Environment variable (for CI/containers)
  3. .env file (dev-only fallback, with warning)

First-run flow: if no credentials exist anywhere, prompts
the user to enter their API key and stores it encrypted.
"""

import getpass
import os
import sys
from pathlib import Path
from typing import Optional

from core.security.encryption import CredentialStore
from core.security.keychain import KeychainManager


# Default paths
_INTENTOS_DIR = Path.home() / ".intentos"
_CREDS_PATH = _INTENTOS_DIR / "credentials.enc"
_KEYCHAIN_FALLBACK = _INTENTOS_DIR / "master_key.enc"


class CredentialProvider:
    """
    Resolves credentials from the most secure available source.

    Usage:
        provider = CredentialProvider()
        api_key = provider.get("ANTHROPIC_API_KEY")
    """

    def __init__(
        self,
        creds_path: Optional[Path] = None,
        keychain_fallback_path: Optional[Path] = None,
        use_os_keychain: bool = True,
    ):
        self._creds_path = creds_path or _CREDS_PATH
        self._keychain = KeychainManager(
            service_name="intentos",
            use_os_keychain=use_os_keychain,
            fallback_path=keychain_fallback_path or _KEYCHAIN_FALLBACK,
        )
        self._store: Optional[CredentialStore] = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the credential store."""
        if self._initialized:
            return

        master_key = self._keychain.get_or_create_master_key()
        self._store = CredentialStore(master_key, storage_path=self._creds_path)

        if self._creds_path.exists():
            self._store.load()

        self._initialized = True

    def get(self, name: str) -> Optional[str]:
        """
        Retrieve a credential by name.

        Resolution order:
          1. Encrypted credential store
          2. Environment variable
          3. None (caller decides what to do)
        """
        # Try encrypted store first
        self._ensure_initialized()
        value = self._store.retrieve(name)
        if value is not None:
            return value

        # Fall back to environment variable
        env_value = os.environ.get(name)
        if env_value:
            return env_value

        return None

    def store(self, name: str, value: str) -> None:
        """Store a credential securely."""
        self._ensure_initialized()
        self._store.store(name, value)
        self._store.save()

    def delete(self, name: str) -> None:
        """Delete a credential."""
        self._ensure_initialized()
        self._store.delete(name)
        self._store.save()

    def has(self, name: str) -> bool:
        """Check if a credential exists (in store or env)."""
        return self.get(name) is not None

    def list_stored(self) -> list[str]:
        """List credential names in the encrypted store."""
        self._ensure_initialized()
        return self._store.list_credentials()

    def prompt_and_store(self, name: str, display_name: str, help_url: str = "") -> str:
        """
        Interactive: prompt the user for a credential and store it securely.

        Returns the credential value.
        """
        print(f"\n  IntentOS needs your {display_name}.")
        if help_url:
            print(f"  Get one at: {help_url}")
        print()

        while True:
            value = getpass.getpass(f"  Paste your {display_name}: ").strip()
            if value:
                break
            print("  That was empty. Please try again.")

        self.store(name, value)
        print(f"\n  Stored securely. Your {display_name} is encrypted on this device.")
        print(f"  It will never be stored in plaintext or transmitted anywhere.\n")
        return value


def get_api_key(provider: Optional[CredentialProvider] = None) -> str:
    """
    Get the Anthropic API key — the primary credential for IntentOS Phase 1.

    If no key exists anywhere, prompts the user interactively.
    Used by the kernel at startup.
    """
    if provider is None:
        provider = CredentialProvider()

    key = provider.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # Check .env as legacy fallback (with warning)
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            key = os.environ.get("ANTHROPIC_API_KEY")
            if key:
                print("\n  Note: Found API key in .env file.")
                print("  For better security, IntentOS will migrate it to encrypted storage.")
                provider.store("ANTHROPIC_API_KEY", key)
                print("  Done. You can now delete the .env file if you wish.\n")
                return key
    except ImportError:
        pass

    # No key found anywhere — prompt user
    return provider.prompt_and_store(
        name="ANTHROPIC_API_KEY",
        display_name="Anthropic API key",
        help_url="https://console.anthropic.com/settings/keys",
    )
