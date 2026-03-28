"""
IntentOS Secrets Manager (Phase 4.6)

Enterprise credential management with rotation, expiration, and access tracking.
Builds on CredentialStore for AES-256-GCM encryption — each secret is individually
encrypted, and the entire store is double-encrypted when persisted to disk.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.security.encryption import CredentialStore, EncryptedBlob


@dataclass
class SecretEntry:
    """Metadata and encrypted value for a single secret."""

    name: str
    encrypted_value: Optional[EncryptedBlob]
    created_at: datetime
    owner: str
    expires_at: Optional[datetime] = None
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    rotated_at: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    return datetime.fromisoformat(s)


class SecretsManager:
    """
    Enterprise secrets manager with rotation, expiration, and access tracking.

    Every secret is individually AES-256-GCM encrypted via CredentialStore.
    Persistence uses double encryption: each secret value + the whole store.
    """

    def __init__(self, master_key: bytes):
        self._credential_store = CredentialStore(master_key)
        self._secrets: dict[str, SecretEntry] = {}
        self._access_logs: dict[str, list[dict]] = {}
        self._rotation_history: dict[str, list[datetime]] = {}

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def store(
        self,
        name: str,
        value: str,
        owner: str,
        expires_in_days: Optional[int] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """Encrypt and store a secret."""
        blob = self._credential_store.encrypt(value, context=name)
        now = _now()
        expires_at = now + timedelta(days=expires_in_days) if expires_in_days else None

        self._secrets[name] = SecretEntry(
            name=name,
            encrypted_value=blob,
            created_at=now,
            owner=owner,
            expires_at=expires_at,
            last_accessed=now,
            access_count=0,
            tags=tags or [],
        )
        self._access_logs.setdefault(name, [])
        self._rotation_history.setdefault(name, [])

    def retrieve(self, name: str, requester: str) -> Optional[str]:
        """
        Retrieve and decrypt a secret. Returns None if not found or expired.
        Updates access tracking on success.
        """
        entry = self._secrets.get(name)
        if entry is None:
            return None

        # Check expiration
        if entry.expires_at is not None and entry.expires_at <= _now():
            return None

        value = self._credential_store.decrypt(entry.encrypted_value, context=name)

        # Track access
        entry.access_count += 1
        entry.last_accessed = _now()
        self._access_logs.setdefault(name, []).append(
            {"requester": requester, "timestamp": _now().isoformat()}
        )

        return value

    def delete(self, name: str, requester: str) -> None:
        """
        Delete a secret. Only the owner or 'admin' can delete.

        Raises:
            KeyError: If secret does not exist.
            PermissionError: If requester is not the owner or admin.
        """
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found")

        entry = self._secrets[name]
        if requester != entry.owner and requester != "admin":
            raise PermissionError(
                f"Only the owner ('{entry.owner}') or admin can delete secret '{name}'"
            )

        del self._secrets[name]
        self._access_logs.pop(name, None)
        self._rotation_history.pop(name, None)

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def rotate(self, name: str, new_value: str, requester: str) -> None:
        """
        Re-encrypt a secret with a new value. Preserves access_count.

        Raises:
            KeyError: If secret does not exist.
        """
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found")

        entry = self._secrets[name]
        blob = self._credential_store.encrypt(new_value, context=name)
        entry.encrypted_value = blob
        entry.rotated_at = _now()

        self._rotation_history.setdefault(name, []).append(entry.rotated_at)

    def get_rotation_history(self, name: str) -> list[datetime]:
        """Return list of past rotation timestamps for a secret."""
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found")
        return list(self._rotation_history.get(name, []))

    # ------------------------------------------------------------------
    # Expiration
    # ------------------------------------------------------------------

    def cleanup_expired(self) -> list[str]:
        """Remove all expired secrets. Returns list of removed names."""
        now = _now()
        expired = [
            name
            for name, entry in self._secrets.items()
            if entry.expires_at is not None and entry.expires_at <= now
        ]
        for name in expired:
            del self._secrets[name]
            self._access_logs.pop(name, None)
            self._rotation_history.pop(name, None)
        return expired

    # ------------------------------------------------------------------
    # Listing and Metadata
    # ------------------------------------------------------------------

    def list_secrets(
        self,
        owner: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[SecretEntry]:
        """
        List secret metadata (never values). Optionally filter by owner/tag.
        Returns SecretEntry objects with encrypted_value set to None.
        """
        results = []
        for entry in self._secrets.values():
            if owner and entry.owner != owner:
                continue
            if tag and tag not in entry.tags:
                continue
            results.append(
                SecretEntry(
                    name=entry.name,
                    encrypted_value=None,
                    created_at=entry.created_at,
                    owner=entry.owner,
                    expires_at=entry.expires_at,
                    last_accessed=entry.last_accessed,
                    access_count=entry.access_count,
                    rotated_at=entry.rotated_at,
                    tags=list(entry.tags),
                )
            )
        return results

    def get_metadata(self, name: str) -> SecretEntry:
        """
        Return metadata for a single secret (value stripped).

        Raises:
            KeyError: If secret does not exist.
        """
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found")

        entry = self._secrets[name]
        return SecretEntry(
            name=entry.name,
            encrypted_value=None,
            created_at=entry.created_at,
            owner=entry.owner,
            expires_at=entry.expires_at,
            last_accessed=entry.last_accessed,
            access_count=entry.access_count,
            rotated_at=entry.rotated_at,
            tags=list(entry.tags),
        )

    # ------------------------------------------------------------------
    # Access Log
    # ------------------------------------------------------------------

    def get_access_log(self, name: str) -> list[dict]:
        """
        Return the access log for a secret.

        Raises:
            KeyError: If secret does not exist.
        """
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found")
        return list(self._access_logs.get(name, []))

    # ------------------------------------------------------------------
    # Persistence (double-encrypted)
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """
        Persist the entire secrets manager to disk.
        Double encrypted: each secret value + the whole serialized store.
        """
        data = {}
        for name, entry in self._secrets.items():
            data[name] = {
                "encrypted_value_json": entry.encrypted_value.to_json(),
                "created_at": _dt_to_str(entry.created_at),
                "owner": entry.owner,
                "expires_at": _dt_to_str(entry.expires_at),
                "last_accessed": _dt_to_str(entry.last_accessed),
                "access_count": entry.access_count,
                "rotated_at": _dt_to_str(entry.rotated_at),
                "tags": entry.tags,
            }

        payload = json.dumps(
            {
                "secrets": data,
                "access_logs": self._access_logs,
                "rotation_history": {
                    k: [dt.isoformat() for dt in v]
                    for k, v in self._rotation_history.items()
                },
            }
        )

        # Outer encryption layer
        outer_blob = self._credential_store.encrypt(payload, context="secrets_manager_store")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(outer_blob.to_bytes())

    def load(self, path: Path) -> None:
        """
        Load the secrets manager from disk. No-op if file does not exist.
        """
        if not path.exists():
            return

        raw = path.read_bytes()
        outer_blob = EncryptedBlob.from_bytes(raw)
        payload = self._credential_store.decrypt(outer_blob, context="secrets_manager_store")
        store_data = json.loads(payload)

        self._secrets = {}
        for name, entry_data in store_data["secrets"].items():
            blob = EncryptedBlob.from_json(entry_data["encrypted_value_json"])
            self._secrets[name] = SecretEntry(
                name=name,
                encrypted_value=blob,
                created_at=_str_to_dt(entry_data["created_at"]),
                owner=entry_data["owner"],
                expires_at=_str_to_dt(entry_data.get("expires_at")),
                last_accessed=_str_to_dt(entry_data.get("last_accessed")),
                access_count=entry_data.get("access_count", 0),
                rotated_at=_str_to_dt(entry_data.get("rotated_at")),
                tags=entry_data.get("tags", []),
            )

        self._access_logs = store_data.get("access_logs", {})
        self._rotation_history = {
            k: [datetime.fromisoformat(dt) for dt in v]
            for k, v in store_data.get("rotation_history", {}).items()
        }
