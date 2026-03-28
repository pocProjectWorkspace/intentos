"""
IntentHub Registry (Phase 4.7)
Public capability registry — discover, version, download, publish.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when a manifest or operation fails validation."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_SNAKE_AGENT_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*_agent$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _validate_manifest_fields(
    name: str,
    version: str,
    description: str,
    author: str,
    **_kwargs: Any,
) -> None:
    if not name or not _SNAKE_AGENT_RE.match(name):
        raise ValidationError(
            f"Invalid name '{name}': must be snake_case ending with '_agent'."
        )
    if not version or not _SEMVER_RE.match(version):
        raise ValidationError(
            f"Invalid version '{version}': must be semver (X.Y.Z)."
        )
    if not description:
        raise ValidationError("description is required and cannot be empty.")
    if not author:
        raise ValidationError("author is required and cannot be empty.")


# ---------------------------------------------------------------------------
# CapabilityManifest
# ---------------------------------------------------------------------------

@dataclass
class CapabilityManifest:
    name: str
    version: str
    description: str
    author: str
    license: str
    category: str
    status: Optional[str]
    permissions: List[str]
    actions: List[str]
    platforms: List[str]
    min_intentos_version: str
    checksum: Optional[str] = None
    signature: Optional[str] = None
    published_at: Optional[str] = None

    def __post_init__(self) -> None:
        # Default status
        if self.status is None:
            self.status = "draft"
        # Validate
        _validate_manifest_fields(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
        )
        # Auto-compute checksum
        if self.checksum is None:
            self.checksum = self._compute_checksum()
        # Timestamp
        if self.published_at is None:
            self.published_at = datetime.now(timezone.utc).isoformat()

    # -- internal helpers --------------------------------------------------

    @classmethod
    def _raw_construct(cls, **kwargs: Any) -> "CapabilityManifest":
        """Bypass __post_init__ — used only for testing invalid paths."""
        obj = object.__new__(cls)
        for k, v in kwargs.items():
            object.__setattr__(obj, k, v)
        # Fill missing attrs so later code won't AttributeError
        for f in (
            "name", "version", "description", "author", "license",
            "category", "status", "permissions", "actions", "platforms",
            "min_intentos_version", "checksum", "signature", "published_at",
        ):
            if not hasattr(obj, f):
                object.__setattr__(obj, f, None)
        return obj

    def _compute_checksum(self) -> str:
        payload = f"{self.name}:{self.version}:{self.description}:{self.author}"
        return hashlib.sha256(payload.encode()).hexdigest()

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "category": self.category,
            "status": self.status,
            "permissions": self.permissions,
            "actions": self.actions,
            "platforms": self.platforms,
            "min_intentos_version": self.min_intentos_version,
            "checksum": self.checksum,
            "signature": self.signature,
            "published_at": self.published_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityManifest":
        return cls(
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            license=data.get("license", ""),
            category=data.get("category", ""),
            status=data.get("status"),
            permissions=data.get("permissions", []),
            actions=data.get("actions", []),
            platforms=data.get("platforms", []),
            min_intentos_version=data.get("min_intentos_version", ""),
            checksum=data.get("checksum"),
            signature=data.get("signature"),
            published_at=data.get("published_at"),
        )


# ---------------------------------------------------------------------------
# RegistryEntry
# ---------------------------------------------------------------------------

@dataclass
class RegistryEntry:
    manifest: CapabilityManifest
    download_url: str
    install_count: int = 0
    rating: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "download_url": self.download_url,
            "install_count": self.install_count,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryEntry":
        return cls(
            manifest=CapabilityManifest.from_dict(data["manifest"]),
            download_url=data["download_url"],
            install_count=data.get("install_count", 0),
            rating=data.get("rating", 0.0),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class Registry:
    """Local capability registry (no network required)."""

    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        # name -> version -> RegistryEntry
        self._entries: Dict[str, Dict[str, RegistryEntry]] = {}

    # -- publish -----------------------------------------------------------

    def publish(self, manifest: CapabilityManifest, bundle_path: str) -> RegistryEntry:
        """Validate *manifest* and register the capability."""
        # Re-validate (catches _raw_construct'd manifests)
        _validate_manifest_fields(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
        )

        name = manifest.name
        version = manifest.version

        if name in self._entries and version in self._entries[name]:
            raise ValidationError(
                f"Capability '{name}' version '{version}' already exists."
            )

        # Store bundle
        dest = os.path.join(self.storage_dir, name, version)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(bundle_path, dest)

        entry = RegistryEntry(
            manifest=manifest,
            download_url=dest,
        )
        self._entries.setdefault(name, {})[version] = entry
        return entry

    # -- lookup ------------------------------------------------------------

    def get(self, name: str) -> Optional[RegistryEntry]:
        """Return the latest-version entry for *name*, or None."""
        versions = self._entries.get(name)
        if not versions:
            return None
        latest = max(versions.keys(), key=_semver_tuple)
        return versions[latest]

    def get_version(self, name: str, version: str) -> Optional[RegistryEntry]:
        return self._entries.get(name, {}).get(version)

    def list_versions(self, name: str) -> List[RegistryEntry]:
        versions = self._entries.get(name, {})
        return sorted(versions.values(), key=lambda e: _semver_tuple(e.manifest.version))

    def list_all(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[RegistryEntry]:
        results: List[RegistryEntry] = []
        for versions in self._entries.values():
            entry = max(versions.values(), key=lambda e: _semver_tuple(e.manifest.version))
            if category and entry.manifest.category != category:
                continue
            if status and entry.manifest.status != status:
                continue
            results.append(entry)
        return results

    # -- search ------------------------------------------------------------

    def search(self, query: str) -> List[RegistryEntry]:
        if not query:
            return self.list_all()
        q = query.lower()
        results: List[RegistryEntry] = []
        for versions in self._entries.values():
            entry = max(versions.values(), key=lambda e: _semver_tuple(e.manifest.version))
            m = entry.manifest
            searchable = f"{m.name} {m.description} {m.category}".lower()
            if q in searchable:
                results.append(entry)
        return results

    # -- install / uninstall -----------------------------------------------

    def install(self, name: str, target_dir: str) -> str:
        entry = self.get(name)
        if entry is None:
            raise ValueError(f"Capability '{name}' not found in registry.")
        dest = os.path.join(target_dir, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(entry.download_url, dest)
        entry.install_count += 1
        return dest

    def uninstall(self, name: str, target_dir: str) -> None:
        dest = os.path.join(target_dir, name)
        if os.path.isdir(dest):
            shutil.rmtree(dest)

    def is_installed(self, name: str, target_dir: str) -> bool:
        return os.path.isdir(os.path.join(target_dir, name))

    # -- updates -----------------------------------------------------------

    def check_updates(
        self, installed: Dict[str, str]
    ) -> List[Dict[str, str]]:
        updates: List[Dict[str, str]] = []
        for name, current_ver in installed.items():
            entry = self.get(name)
            if entry is None:
                continue
            if _semver_tuple(entry.manifest.version) > _semver_tuple(current_ver):
                updates.append({
                    "name": name,
                    "installed_version": current_ver,
                    "latest_version": entry.manifest.version,
                })
        return updates

    # -- statistics --------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        total = 0
        by_category: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        total_installs = 0

        for versions in self._entries.values():
            latest = max(versions.values(), key=lambda e: _semver_tuple(e.manifest.version))
            total += 1
            cat = latest.manifest.category
            st = latest.manifest.status
            by_category[cat] = by_category.get(cat, 0) + 1
            by_status[st] = by_status.get(st, 0) + 1
            for entry in versions.values():
                total_installs += entry.install_count

        return {
            "total_capabilities": total,
            "by_category": by_category,
            "by_status": by_status,
            "total_installs": total_installs,
        }

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        data: List[Dict[str, Any]] = []
        for versions in self._entries.values():
            for entry in versions.values():
                data.append(entry.to_dict())
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Registry file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        self._entries.clear()
        for item in data:
            entry = RegistryEntry.from_dict(item)
            name = entry.manifest.name
            version = entry.manifest.version
            self._entries.setdefault(name, {})[version] = entry


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _semver_tuple(version: str) -> tuple:
    try:
        return tuple(int(p) for p in version.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)
