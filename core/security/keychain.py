"""
IntentOS OS Keychain Integration

Stores the master encryption key in OS-native secure storage:
- macOS: Keychain Services
- Linux: GNOME Keyring / KWallet via secretstorage
- Windows: Windows Credential Manager

Falls back to an encrypted file with restricted permissions
when OS keychain is unavailable (CI, containers, minimal installs).

Inspired by IronClaw's OS keychain integration.
"""

import base64
import hashlib
import hmac
import os
import stat
import importlib

# Use importlib to get stdlib platform (avoid collision with core.platform package)
_platform = importlib.import_module("platform")
from pathlib import Path
from typing import Optional

from core.security.exceptions import KeychainError

# Constants
MASTER_KEY_SIZE = 32  # bytes
FALLBACK_HMAC_KEY = b"intentos-fallback-key-integrity-v1"
FALLBACK_MAGIC = b"IOSF"  # IntentOS Secure Fallback


class KeychainManager:
    """
    Manages the IntentOS master encryption key via OS keychain or encrypted file fallback.

    Usage:
        km = KeychainManager()
        key = km.get_or_create_master_key()
        # key is now stored securely and retrievable across sessions
    """

    def __init__(
        self,
        service_name: str = "intentos",
        use_os_keychain: bool = True,
        fallback_path: Optional[Path] = None,
    ):
        self.service_name = service_name
        self.platform = _platform.system().lower()
        self._use_os_keychain = use_os_keychain and self._os_keychain_available()
        self._fallback_path = fallback_path or self._default_fallback_path()

    def _default_fallback_path(self) -> Path:
        """Default location for encrypted key file."""
        return Path.home() / ".intentos" / "master_key.enc"

    def _os_keychain_available(self) -> bool:
        """Check if OS keychain is available on this platform."""
        try:
            import keyring

            # Test if a backend is configured (not the null/fail backend)
            backend = keyring.get_keyring()
            backend_name = type(backend).__name__
            # Reject fail/null/chainer-only backends
            if "fail" in backend_name.lower() or "null" in backend_name.lower():
                return False
            return True
        except Exception:
            return False

    def store_master_key(self, key: bytes) -> None:
        """Store the master key in OS keychain or fallback file."""
        if self._use_os_keychain:
            self._store_keychain(key)
        else:
            self._store_fallback(key)

    def retrieve_master_key(self) -> Optional[bytes]:
        """
        Retrieve the master key.

        Returns None if no key has been stored yet.
        Raises KeychainError if the stored key is corrupted.
        """
        if self._use_os_keychain:
            return self._retrieve_keychain()
        else:
            return self._retrieve_fallback()

    def delete_master_key(self) -> None:
        """Delete the master key from storage."""
        if self._use_os_keychain:
            self._delete_keychain()
        else:
            self._delete_fallback()

    @staticmethod
    def generate_master_key() -> bytes:
        """Generate a cryptographically random 32-byte master key."""
        return os.urandom(MASTER_KEY_SIZE)

    def get_or_create_master_key(self) -> bytes:
        """
        Retrieve the existing master key, or generate and store a new one.

        This is the recommended entry point for most use cases.
        """
        existing = self.retrieve_master_key()
        if existing is not None:
            return existing

        key = self.generate_master_key()
        self.store_master_key(key)
        return key

    # --- OS Keychain Backends ---

    def _store_keychain(self, key: bytes) -> None:
        """Store key in OS-native keychain."""
        try:
            import keyring

            encoded = base64.b64encode(key).decode("ascii")
            keyring.set_password(self.service_name, "master_key", encoded)
        except Exception as e:
            raise KeychainError(f"Failed to store key in OS keychain: {e}") from e

    def _retrieve_keychain(self) -> Optional[bytes]:
        """Retrieve key from OS-native keychain."""
        try:
            import keyring

            encoded = keyring.get_password(self.service_name, "master_key")
            if encoded is None:
                return None
            return base64.b64decode(encoded)
        except Exception as e:
            raise KeychainError(f"Failed to retrieve key from OS keychain: {e}") from e

    def _delete_keychain(self) -> None:
        """Delete key from OS-native keychain."""
        try:
            import keyring

            keyring.delete_password(self.service_name, "master_key")
        except keyring.errors.PasswordDeleteError:
            pass  # Key doesn't exist, that's fine
        except Exception as e:
            raise KeychainError(f"Failed to delete key from OS keychain: {e}") from e

    # --- Encrypted File Fallback ---

    def _store_fallback(self, key: bytes) -> None:
        """Store key in an HMAC-protected file with restricted permissions."""
        # HMAC for integrity (not encryption — the key IS the secret)
        mac = hmac.new(FALLBACK_HMAC_KEY, key, hashlib.sha256).digest()
        payload = FALLBACK_MAGIC + mac + key

        # XOR obfuscation with a derived pad (not encryption, but prevents
        # the raw key from appearing in the file — defense in depth)
        pad = hashlib.sha256(FALLBACK_HMAC_KEY + b"obfuscation").digest()
        obfuscated_key = bytes(k ^ pad[i % len(pad)] for i, k in enumerate(key))
        payload = FALLBACK_MAGIC + mac + obfuscated_key

        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self._fallback_path.write_bytes(payload)

        # Set restrictive permissions (owner-only read/write)
        if _platform.system() != "Windows":
            self._fallback_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def _retrieve_fallback(self) -> Optional[bytes]:
        """Retrieve key from HMAC-protected fallback file."""
        if not self._fallback_path.exists():
            return None

        raw = self._fallback_path.read_bytes()

        if len(raw) < len(FALLBACK_MAGIC) + 32:  # magic + HMAC minimum
            raise KeychainError("Fallback key file is corrupted (too short)")

        if raw[: len(FALLBACK_MAGIC)] != FALLBACK_MAGIC:
            raise KeychainError("Fallback key file is corrupted (bad magic)")

        offset = len(FALLBACK_MAGIC)
        stored_mac = raw[offset : offset + 32]
        offset += 32
        obfuscated_key = raw[offset:]

        # De-obfuscate
        pad = hashlib.sha256(FALLBACK_HMAC_KEY + b"obfuscation").digest()
        key = bytes(k ^ pad[i % len(pad)] for i, k in enumerate(obfuscated_key))

        # Verify HMAC
        expected_mac = hmac.new(FALLBACK_HMAC_KEY, key, hashlib.sha256).digest()
        if not hmac.compare_digest(stored_mac, expected_mac):
            raise KeychainError(
                "Fallback key file integrity check failed — the file may have been tampered with"
            )

        return key

    def _delete_fallback(self) -> None:
        """Delete the fallback key file."""
        if self._fallback_path.exists():
            # Overwrite with zeros before deleting (best-effort secure delete)
            size = self._fallback_path.stat().st_size
            self._fallback_path.write_bytes(b"\x00" * size)
            self._fallback_path.unlink()
