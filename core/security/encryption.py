"""
IntentOS Credential Encryption Module

AES-256-GCM authenticated encryption with HKDF-SHA256 key derivation.
Every secret gets a unique salt and nonce. Tampered data is detected
and rejected via GCM authentication tags.

Inspired by IronClaw's credential protection architecture.
"""

import base64
import json
import os
import struct
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from core.security.exceptions import (
    DecryptionError,
    EncryptionError,
    MasterKeyError,
    TamperedDataError,
)

# Constants
SALT_SIZE = 32      # bytes — unique per encryption
NONCE_SIZE = 12     # bytes — AES-GCM standard
KEY_SIZE = 32       # bytes — AES-256
MIN_MASTER_KEY = 32 # bytes — minimum master key length

# Binary format: MAGIC(4) + SALT(32) + NONCE(12) + CIPHERTEXT(variable)
BLOB_MAGIC = b"IOS1"  # IntentOS Security v1


class EncryptedBlob:
    """Container for encrypted data with salt, nonce, and ciphertext."""

    __slots__ = ("salt", "nonce", "ciphertext")

    def __init__(self, salt: bytes, nonce: bytes, ciphertext: bytes):
        self.salt = salt
        self.nonce = nonce
        self.ciphertext = ciphertext

    def to_bytes(self) -> bytes:
        """Serialize to binary format: MAGIC + SALT + NONCE + CIPHERTEXT."""
        return (
            BLOB_MAGIC
            + struct.pack(">I", len(self.ciphertext))
            + self.salt
            + self.nonce
            + self.ciphertext
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedBlob":
        """Deserialize from binary format."""
        min_size = len(BLOB_MAGIC) + 4 + SALT_SIZE + NONCE_SIZE + 1
        if len(data) < min_size:
            raise ValueError(
                "Data too short to be a valid encrypted blob"
            )

        if data[:4] != BLOB_MAGIC:
            raise ValueError("Invalid blob magic bytes — not an IntentOS encrypted blob")

        offset = 4
        ct_len = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4

        salt = data[offset : offset + SALT_SIZE]
        offset += SALT_SIZE

        nonce = data[offset : offset + NONCE_SIZE]
        offset += NONCE_SIZE

        ciphertext = data[offset : offset + ct_len]
        if len(ciphertext) != ct_len:
            raise ValueError("Truncated ciphertext in blob")

        return cls(salt=salt, nonce=nonce, ciphertext=ciphertext)

    def to_json(self) -> str:
        """Serialize to JSON with base64-encoded binary fields."""
        return json.dumps(
            {
                "version": 1,
                "salt": base64.b64encode(self.salt).decode(),
                "nonce": base64.b64encode(self.nonce).decode(),
                "ciphertext": base64.b64encode(self.ciphertext).decode(),
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> "EncryptedBlob":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        if "salt" not in data or "nonce" not in data or "ciphertext" not in data:
            raise KeyError("Missing required fields in encrypted blob JSON")
        return cls(
            salt=base64.b64decode(data["salt"]),
            nonce=base64.b64decode(data["nonce"]),
            ciphertext=base64.b64decode(data["ciphertext"]),
        )


def _derive_key(master_key: bytes, salt: bytes) -> bytes:
    """Derive a per-secret AES-256 key from master key + unique salt using HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        info=b"intentos-credential-encryption-v1",
    )
    return hkdf.derive(master_key)


class CredentialStore:
    """
    AES-256-GCM credential encryption with HKDF-SHA256 key derivation.

    Each encryption uses a unique random salt and nonce, so encrypting
    the same plaintext twice always produces different ciphertext.

    Usage:
        store = CredentialStore(master_key)
        blob = store.encrypt("my-api-key", context="anthropic")
        plaintext = store.decrypt(blob, context="anthropic")

    High-level API:
        store = CredentialStore(master_key, storage_path=Path("creds.enc"))
        store.store("anthropic_key", "sk-ant-...")
        key = store.retrieve("anthropic_key")
    """

    def __init__(
        self,
        master_key: bytes,
        storage_path: Optional[Path] = None,
    ):
        if len(master_key) < MIN_MASTER_KEY:
            raise MasterKeyError(
                f"Master key must be at least {MIN_MASTER_KEY} bytes, "
                f"got {len(master_key)} bytes"
            )
        self._master_key = master_key
        self._storage_path = storage_path
        self._credentials: dict[str, EncryptedBlob] = {}

    def encrypt(self, plaintext: str, context: str = "") -> EncryptedBlob:
        """
        Encrypt plaintext with a unique salt and nonce.

        Args:
            plaintext: The secret to encrypt.
            context: Label for this secret (used for logging, not cryptographic).

        Returns:
            EncryptedBlob containing salt, nonce, and ciphertext.
        """
        try:
            salt = os.urandom(SALT_SIZE)
            nonce = os.urandom(NONCE_SIZE)
            derived_key = _derive_key(self._master_key, salt)
            aesgcm = AESGCM(derived_key)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            return EncryptedBlob(salt=salt, nonce=nonce, ciphertext=ciphertext)
        except Exception as e:
            if isinstance(e, (EncryptionError, MasterKeyError)):
                raise
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, blob: EncryptedBlob, context: str = "") -> str:
        """
        Decrypt an EncryptedBlob back to plaintext.

        Args:
            blob: The encrypted data to decrypt.
            context: Label for this secret (used for logging, not cryptographic).

        Returns:
            The original plaintext string.

        Raises:
            DecryptionError: If decryption fails (wrong key, tampered data, etc.)
        """
        try:
            derived_key = _derive_key(self._master_key, blob.salt)
            aesgcm = AESGCM(derived_key)
            plaintext_bytes = aesgcm.decrypt(blob.nonce, blob.ciphertext, None)
            return plaintext_bytes.decode("utf-8")
        except Exception as e:
            if isinstance(e, DecryptionError):
                raise
            raise DecryptionError(
                "Decryption failed — the key may be wrong or the data may have been tampered with"
            ) from e

    # --- High-Level Credential Management API ---

    def store(self, name: str, value: str) -> None:
        """Store a named credential (encrypted in memory)."""
        blob = self.encrypt(value, context=name)
        self._credentials[name] = blob

    def retrieve(self, name: str) -> Optional[str]:
        """Retrieve a named credential. Returns None if not found."""
        blob = self._credentials.get(name)
        if blob is None:
            return None
        return self.decrypt(blob, context=name)

    def delete(self, name: str) -> None:
        """Delete a named credential. No-op if not found."""
        self._credentials.pop(name, None)

    def list_credentials(self) -> list[str]:
        """List all stored credential names (not values)."""
        return list(self._credentials.keys())

    def save(self) -> None:
        """Persist all credentials to disk (encrypted)."""
        if self._storage_path is None:
            raise EncryptionError("No storage path configured")

        data = {}
        for name, blob in self._credentials.items():
            data[name] = blob.to_json()

        # Encrypt the entire credential map as a second layer
        payload = json.dumps(data)
        outer_blob = self.encrypt(payload, context="credential_store")

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_bytes(outer_blob.to_bytes())

    def load(self) -> None:
        """Load credentials from disk."""
        if self._storage_path is None:
            raise EncryptionError("No storage path configured")

        if not self._storage_path.exists():
            return

        raw = self._storage_path.read_bytes()
        outer_blob = EncryptedBlob.from_bytes(raw)
        payload = self.decrypt(outer_blob, context="credential_store")
        data = json.loads(payload)

        self._credentials = {}
        for name, blob_json in data.items():
            self._credentials[name] = EncryptedBlob.from_json(blob_json)
