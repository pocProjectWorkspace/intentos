"""
TDD RED Phase: Tests for IntentOS OS Keychain Integration.

Tests KeychainManager — storing master keys in OS-native
secure storage (macOS Keychain, Linux GNOME Keyring, Windows
Credential Manager) with encrypted file fallback.
"""

import os
import platform
import pytest
from pathlib import Path


# --- Test Fixtures ---


@pytest.fixture
def fallback_path(tmp_path) -> Path:
    """Temporary path for encrypted file fallback."""
    return tmp_path / "intentos_master_key.enc"


@pytest.fixture
def keychain(fallback_path):
    """KeychainManager using file fallback (works in all test environments)."""
    from core.security.keychain import KeychainManager

    return KeychainManager(
        service_name="intentos-test",
        use_os_keychain=False,  # force file fallback for test reliability
        fallback_path=fallback_path,
    )


@pytest.fixture
def master_key() -> bytes:
    """A valid 32-byte master key."""
    return os.urandom(32)


# --- Initialization Tests ---


class TestKeychainInit:
    """Tests for KeychainManager initialization."""

    def test_creates_instance(self, fallback_path):
        from core.security.keychain import KeychainManager

        km = KeychainManager(
            service_name="intentos-test",
            use_os_keychain=False,
            fallback_path=fallback_path,
        )
        assert km is not None

    def test_default_service_name(self, fallback_path):
        from core.security.keychain import KeychainManager

        km = KeychainManager(fallback_path=fallback_path, use_os_keychain=False)
        assert km.service_name == "intentos"

    def test_detects_platform(self):
        from core.security.keychain import KeychainManager

        km = KeychainManager(use_os_keychain=False)
        assert km.platform in ("darwin", "linux", "windows")


# --- Store and Retrieve Tests ---


class TestStoreAndRetrieve:
    """Core functionality: store a master key and get it back."""

    def test_store_and_retrieve(self, keychain, master_key):
        keychain.store_master_key(master_key)
        result = keychain.retrieve_master_key()
        assert result == master_key

    def test_store_overwrites_existing(self, keychain, master_key):
        keychain.store_master_key(master_key)
        new_key = os.urandom(32)
        keychain.store_master_key(new_key)
        result = keychain.retrieve_master_key()
        assert result == new_key

    def test_retrieve_when_no_key_stored(self, keychain):
        result = keychain.retrieve_master_key()
        assert result is None

    def test_store_64_byte_key(self, keychain):
        key = os.urandom(64)
        keychain.store_master_key(key)
        result = keychain.retrieve_master_key()
        assert result == key


# --- Delete Tests ---


class TestDelete:
    """Tests for key deletion."""

    def test_delete_existing_key(self, keychain, master_key):
        keychain.store_master_key(master_key)
        keychain.delete_master_key()
        result = keychain.retrieve_master_key()
        assert result is None

    def test_delete_nonexistent_does_not_raise(self, keychain):
        keychain.delete_master_key()  # should not raise


# --- File Fallback Tests ---


class TestFileFallback:
    """Tests for encrypted file fallback when OS keychain is unavailable."""

    def test_fallback_file_created(self, keychain, master_key, fallback_path):
        keychain.store_master_key(master_key)
        assert fallback_path.exists()

    def test_fallback_file_not_plaintext(self, keychain, master_key, fallback_path):
        keychain.store_master_key(master_key)
        raw = fallback_path.read_bytes()
        # Master key should NOT appear in raw file contents
        assert master_key not in raw

    def test_fallback_file_permissions(self, keychain, master_key, fallback_path):
        """Fallback file should be owner-only readable (mode 0o600 on Unix)."""
        keychain.store_master_key(master_key)
        if platform.system() != "Windows":
            mode = oct(fallback_path.stat().st_mode)[-3:]
            assert mode == "600"

    def test_fallback_survives_reload(self, master_key, fallback_path):
        """New KeychainManager instance reads key from existing fallback file."""
        from core.security.keychain import KeychainManager

        km1 = KeychainManager(
            service_name="intentos-test",
            use_os_keychain=False,
            fallback_path=fallback_path,
        )
        km1.store_master_key(master_key)

        km2 = KeychainManager(
            service_name="intentos-test",
            use_os_keychain=False,
            fallback_path=fallback_path,
        )
        result = km2.retrieve_master_key()
        assert result == master_key

    def test_tampered_fallback_file_rejected(self, keychain, master_key, fallback_path):
        from core.security.exceptions import KeychainError

        keychain.store_master_key(master_key)

        # Tamper with the file
        raw = bytearray(fallback_path.read_bytes())
        if len(raw) > 10:
            raw[10] ^= 0xFF
        fallback_path.write_bytes(bytes(raw))

        with pytest.raises((KeychainError, Exception)):
            keychain.retrieve_master_key()


# --- Key Generation Tests ---


class TestKeyGeneration:
    """Tests for automatic master key generation."""

    def test_generate_master_key(self, keychain):
        from core.security.keychain import KeychainManager

        key = KeychainManager.generate_master_key()
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_generated_keys_are_unique(self):
        from core.security.keychain import KeychainManager

        keys = [KeychainManager.generate_master_key() for _ in range(100)]
        assert len(set(keys)) == 100

    def test_get_or_create_creates_new(self, keychain):
        """If no key exists, get_or_create generates and stores one."""
        key = keychain.get_or_create_master_key()
        assert isinstance(key, bytes)
        assert len(key) == 32
        # Should be retrievable now
        assert keychain.retrieve_master_key() == key

    def test_get_or_create_returns_existing(self, keychain, master_key):
        """If a key exists, get_or_create returns it without overwriting."""
        keychain.store_master_key(master_key)
        result = keychain.get_or_create_master_key()
        assert result == master_key


# --- Integration with CredentialStore ---


class TestKeychainCredentialStoreIntegration:
    """End-to-end: KeychainManager provides key for CredentialStore."""

    def test_keychain_provides_key_for_credential_store(self, keychain):
        from core.security.encryption import CredentialStore

        master_key = keychain.get_or_create_master_key()
        store = CredentialStore(master_key)
        store.store("test_key", "test_value")
        assert store.retrieve("test_key") == "test_value"

    def test_credential_store_survives_keychain_reload(self, master_key, fallback_path, tmp_path):
        from core.security.keychain import KeychainManager
        from core.security.encryption import CredentialStore

        creds_path = tmp_path / "creds.enc"

        # Session 1: store credentials
        km1 = KeychainManager(
            service_name="intentos-test",
            use_os_keychain=False,
            fallback_path=fallback_path,
        )
        km1.store_master_key(master_key)
        store1 = CredentialStore(master_key, storage_path=creds_path)
        store1.store("api_key", "sk-secret-123")
        store1.save()

        # Session 2: reload everything from disk
        km2 = KeychainManager(
            service_name="intentos-test",
            use_os_keychain=False,
            fallback_path=fallback_path,
        )
        recovered_key = km2.retrieve_master_key()
        store2 = CredentialStore(recovered_key, storage_path=creds_path)
        store2.load()
        assert store2.retrieve("api_key") == "sk-secret-123"
