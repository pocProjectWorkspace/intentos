"""
TDD RED Phase: Tests for IntentOS Credential Encryption Module.

Tests AES-256-GCM encryption with HKDF-SHA256 key derivation.
Every test here MUST FAIL before implementation exists.
"""

import os
import pytest


# --- Test Fixtures ---


@pytest.fixture
def master_key() -> bytes:
    """A valid 32-byte master key."""
    return os.urandom(32)


@pytest.fixture
def credential_store(master_key):
    """A CredentialStore instance with a valid master key."""
    from core.security.encryption import CredentialStore

    return CredentialStore(master_key)


@pytest.fixture
def second_master_key() -> bytes:
    """A different 32-byte master key for cross-key tests."""
    return os.urandom(32)


@pytest.fixture
def second_store(second_master_key):
    """A CredentialStore with a different master key."""
    from core.security.encryption import CredentialStore

    return CredentialStore(second_master_key)


# --- Initialization Tests ---


class TestCredentialStoreInit:
    """Tests for CredentialStore initialization and key validation."""

    def test_accepts_32_byte_key(self, master_key):
        from core.security.encryption import CredentialStore

        store = CredentialStore(master_key)
        assert store is not None

    def test_accepts_64_byte_key(self):
        from core.security.encryption import CredentialStore

        key = os.urandom(64)
        store = CredentialStore(key)
        assert store is not None

    def test_rejects_short_key(self):
        from core.security.encryption import CredentialStore
        from core.security.exceptions import MasterKeyError

        with pytest.raises(MasterKeyError):
            CredentialStore(b"too-short")

    def test_rejects_31_byte_key(self):
        from core.security.encryption import CredentialStore
        from core.security.exceptions import MasterKeyError

        with pytest.raises(MasterKeyError):
            CredentialStore(os.urandom(31))

    def test_rejects_empty_key(self):
        from core.security.encryption import CredentialStore
        from core.security.exceptions import MasterKeyError

        with pytest.raises(MasterKeyError):
            CredentialStore(b"")


# --- Encryption/Decryption Roundtrip Tests ---


class TestEncryptDecryptRoundtrip:
    """Core roundtrip tests: encrypt then decrypt returns original plaintext."""

    def test_roundtrip_simple_string(self, credential_store):
        plaintext = "sk-ant-api03-secret-key-here"
        blob = credential_store.encrypt(plaintext, context="anthropic_api_key")
        result = credential_store.decrypt(blob, context="anthropic_api_key")
        assert result == plaintext

    def test_roundtrip_empty_string(self, credential_store):
        plaintext = ""
        blob = credential_store.encrypt(plaintext, context="empty_test")
        result = credential_store.decrypt(blob, context="empty_test")
        assert result == plaintext

    def test_roundtrip_unicode(self, credential_store):
        plaintext = "パスワード-密码-كلمة-السر"
        blob = credential_store.encrypt(plaintext, context="unicode_cred")
        result = credential_store.decrypt(blob, context="unicode_cred")
        assert result == plaintext

    def test_roundtrip_large_payload(self, credential_store):
        plaintext = "A" * 100_000  # 100KB credential (e.g., a PEM key)
        blob = credential_store.encrypt(plaintext, context="large_key")
        result = credential_store.decrypt(blob, context="large_key")
        assert result == plaintext

    def test_roundtrip_special_characters(self, credential_store):
        plaintext = 'key="value"&token=abc\n\t\x00\xff'
        blob = credential_store.encrypt(plaintext, context="special")
        result = credential_store.decrypt(blob, context="special")
        assert result == plaintext

    def test_roundtrip_json_payload(self, credential_store):
        import json

        payload = json.dumps({"api_key": "sk-12345", "org": "org-67890"})
        blob = credential_store.encrypt(payload, context="json_creds")
        result = credential_store.decrypt(blob, context="json_creds")
        assert result == payload


# --- Salt and Nonce Uniqueness Tests ---


class TestSaltAndNonceUniqueness:
    """Every encryption must produce unique salt and nonce."""

    def test_same_plaintext_different_blobs(self, credential_store):
        """Encrypting the same string twice must produce different ciphertext."""
        plaintext = "same-secret-twice"
        blob1 = credential_store.encrypt(plaintext, context="test")
        blob2 = credential_store.encrypt(plaintext, context="test")
        assert blob1.ciphertext != blob2.ciphertext

    def test_unique_salts(self, credential_store):
        """Each encryption must use a unique salt."""
        blob1 = credential_store.encrypt("secret1", context="a")
        blob2 = credential_store.encrypt("secret2", context="b")
        assert blob1.salt != blob2.salt

    def test_unique_nonces(self, credential_store):
        """Each encryption must use a unique nonce."""
        blob1 = credential_store.encrypt("secret1", context="a")
        blob2 = credential_store.encrypt("secret2", context="b")
        assert blob1.nonce != blob2.nonce

    def test_hundred_encryptions_all_unique(self, credential_store):
        """100 encryptions of the same plaintext must all be unique."""
        blobs = [
            credential_store.encrypt("same", context="bulk")
            for _ in range(100)
        ]
        ciphertexts = [b.ciphertext for b in blobs]
        assert len(set(ciphertexts)) == 100


# --- Cross-Key Isolation Tests ---


class TestCrossKeyIsolation:
    """Ciphertext encrypted with key A must not decrypt with key B."""

    def test_wrong_key_fails(self, credential_store, second_store):
        from core.security.exceptions import DecryptionError

        plaintext = "secret-for-key-a"
        blob = credential_store.encrypt(plaintext, context="test")
        with pytest.raises(DecryptionError):
            second_store.decrypt(blob, context="test")

    def test_same_key_different_instances(self, master_key):
        """Two stores with the same key must decrypt each other's data."""
        from core.security.encryption import CredentialStore

        store_a = CredentialStore(master_key)
        store_b = CredentialStore(master_key)
        blob = store_a.encrypt("shared-secret", context="test")
        result = store_b.decrypt(blob, context="test")
        assert result == "shared-secret"


# --- Tamper Detection Tests ---


class TestTamperDetection:
    """AES-GCM must detect any modification to ciphertext, nonce, salt, or tag."""

    def test_tampered_ciphertext(self, credential_store):
        from core.security.exceptions import DecryptionError

        blob = credential_store.encrypt("secret", context="test")
        # Flip a byte in the ciphertext
        tampered = bytearray(blob.ciphertext)
        tampered[0] ^= 0xFF
        blob.ciphertext = bytes(tampered)
        with pytest.raises(DecryptionError):
            credential_store.decrypt(blob, context="test")

    def test_tampered_nonce(self, credential_store):
        from core.security.exceptions import DecryptionError

        blob = credential_store.encrypt("secret", context="test")
        tampered = bytearray(blob.nonce)
        tampered[0] ^= 0xFF
        blob.nonce = bytes(tampered)
        with pytest.raises(DecryptionError):
            credential_store.decrypt(blob, context="test")

    def test_tampered_salt(self, credential_store):
        from core.security.exceptions import DecryptionError

        blob = credential_store.encrypt("secret", context="test")
        tampered = bytearray(blob.salt)
        tampered[0] ^= 0xFF
        blob.salt = bytes(tampered)
        with pytest.raises(DecryptionError):
            credential_store.decrypt(blob, context="test")

    def test_truncated_ciphertext(self, credential_store):
        from core.security.exceptions import DecryptionError

        blob = credential_store.encrypt("secret", context="test")
        blob.ciphertext = blob.ciphertext[:5]
        with pytest.raises(DecryptionError):
            credential_store.decrypt(blob, context="test")

    def test_empty_ciphertext(self, credential_store):
        from core.security.exceptions import DecryptionError

        blob = credential_store.encrypt("secret", context="test")
        blob.ciphertext = b""
        with pytest.raises(DecryptionError):
            credential_store.decrypt(blob, context="test")


# --- EncryptedBlob Serialization Tests ---


class TestEncryptedBlobSerialization:
    """EncryptedBlob must serialize to/from bytes and JSON for storage."""

    def test_to_bytes_roundtrip(self, credential_store):
        from core.security.encryption import EncryptedBlob

        blob = credential_store.encrypt("secret", context="test")
        raw = blob.to_bytes()
        assert isinstance(raw, bytes)
        restored = EncryptedBlob.from_bytes(raw)
        result = credential_store.decrypt(restored, context="test")
        assert result == "secret"

    def test_to_json_roundtrip(self, credential_store):
        from core.security.encryption import EncryptedBlob
        import json

        blob = credential_store.encrypt("secret", context="test")
        json_str = blob.to_json()
        parsed = json.loads(json_str)  # must be valid JSON
        assert "ciphertext" in parsed
        assert "nonce" in parsed
        assert "salt" in parsed
        restored = EncryptedBlob.from_json(json_str)
        result = credential_store.decrypt(restored, context="test")
        assert result == "secret"

    def test_from_bytes_rejects_garbage(self):
        from core.security.encryption import EncryptedBlob
        from core.security.exceptions import DecryptionError

        with pytest.raises((DecryptionError, ValueError)):
            EncryptedBlob.from_bytes(b"not-a-valid-blob")

    def test_from_json_rejects_garbage(self):
        from core.security.encryption import EncryptedBlob
        from core.security.exceptions import DecryptionError

        with pytest.raises((DecryptionError, ValueError, KeyError)):
            EncryptedBlob.from_json('{"garbage": true}')


# --- Secure Credential Manager Tests ---


class TestSecureCredentialManager:
    """High-level API for storing and retrieving named credentials."""

    def test_store_and_retrieve(self, credential_store):
        credential_store.store("anthropic_key", "sk-ant-secret-123")
        result = credential_store.retrieve("anthropic_key")
        assert result == "sk-ant-secret-123"

    def test_retrieve_nonexistent_returns_none(self, credential_store):
        result = credential_store.retrieve("does_not_exist")
        assert result is None

    def test_overwrite_credential(self, credential_store):
        credential_store.store("key", "old-value")
        credential_store.store("key", "new-value")
        result = credential_store.retrieve("key")
        assert result == "new-value"

    def test_delete_credential(self, credential_store):
        credential_store.store("key", "value")
        credential_store.delete("key")
        result = credential_store.retrieve("key")
        assert result is None

    def test_delete_nonexistent_does_not_raise(self, credential_store):
        credential_store.delete("does_not_exist")  # should not raise

    def test_list_credentials(self, credential_store):
        credential_store.store("key_a", "val_a")
        credential_store.store("key_b", "val_b")
        names = credential_store.list_credentials()
        assert "key_a" in names
        assert "key_b" in names

    def test_credentials_persisted_to_file(self, credential_store, tmp_path):
        """Credentials must survive store reload from disk."""
        from core.security.encryption import CredentialStore

        store_path = tmp_path / "creds.enc"
        store = CredentialStore(credential_store._master_key, storage_path=store_path)
        store.store("api_key", "sk-test-persist")
        store.save()

        # New instance, same key, same file
        store2 = CredentialStore(credential_store._master_key, storage_path=store_path)
        store2.load()
        assert store2.retrieve("api_key") == "sk-test-persist"
