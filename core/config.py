"""IntentOS Configuration System.

Provides persistent settings, filesystem grants, and workspace management.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default base path
# ---------------------------------------------------------------------------
DEFAULT_BASE_PATH = Path.home() / ".intentos"

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    """User-facing configuration stored in settings.json."""

    privacy_mode: str = "smart_routing"
    local_model: str = "gemma4:e4b"
    cloud_model: str = "claude-sonnet-4-20250514"
    cloud_provider: str = "anthropic"
    auto_compact_threshold: int = 50
    max_context_tokens: int = 4000
    theme: str = "dark"
    language: str = "en"
    verbose: bool = False
    ollama_models: List[str] = field(default_factory=list)
    embedding_model: str = ""


def load_settings(base_path: Path = DEFAULT_BASE_PATH) -> Settings:
    """Load settings from *base_path*/settings.json, returning defaults on error."""
    settings_file = base_path / "settings.json"
    if not settings_file.exists():
        return Settings()
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings.json root is not an object")
        return Settings(**{k: v for k, v in data.items()
                          if k in Settings.__dataclass_fields__})
    except Exception:
        logger.warning("Corrupted or invalid settings.json — returning defaults")
        return Settings()


def save_settings(settings: Settings, base_path: Path = DEFAULT_BASE_PATH) -> None:
    """Persist *settings* to *base_path*/settings.json."""
    base_path.mkdir(parents=True, exist_ok=True)
    settings_file = base_path / "settings.json"
    settings_file.write_text(
        json.dumps(asdict(settings), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.chmod(settings_file, 0o644)


def update_settings(updates: dict, base_path: Path = DEFAULT_BASE_PATH) -> Settings:
    """Merge *updates* into the existing settings and persist."""
    settings = load_settings(base_path)
    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    save_settings(settings, base_path)
    return settings


# ---------------------------------------------------------------------------
# Grants
# ---------------------------------------------------------------------------

@dataclass
class GrantedPath:
    """A single filesystem path grant."""

    path: str
    access: str  # "read" or "read_write"
    recursive: bool
    granted_at: datetime


@dataclass
class Grants:
    """Filesystem access grants stored in grants.json."""

    version: str = "1.0"
    user: str = ""
    granted_paths: List[GrantedPath] = field(default_factory=list)
    denied_paths: List[str] = field(default_factory=list)
    allow_external_drives: bool = False
    allow_network_drives: bool = False


def _default_grants() -> Grants:
    """Return the factory-default grants object."""
    now = datetime.now()
    return Grants(
        version="1.0",
        user=os.environ.get("USER", "unknown"),
        granted_paths=[
            GrantedPath(path="~/Documents", access="read", recursive=True, granted_at=now),
            GrantedPath(path="~/Downloads", access="read", recursive=True, granted_at=now),
            GrantedPath(path="~/Desktop", access="read", recursive=True, granted_at=now),
            GrantedPath(path="~/.intentos/workspace", access="read_write", recursive=True, granted_at=now),
        ],
        denied_paths=["~/.ssh", "~/.aws", "~/.gnupg", "~/.env"],
        allow_external_drives=False,
        allow_network_drives=False,
    )


def _granted_path_to_dict(gp: GrantedPath) -> dict:
    return {
        "path": gp.path,
        "access": gp.access,
        "recursive": gp.recursive,
        "granted_at": gp.granted_at.isoformat(),
    }


def _granted_path_from_dict(d: dict) -> GrantedPath:
    return GrantedPath(
        path=d["path"],
        access=d["access"],
        recursive=d.get("recursive", True),
        granted_at=datetime.fromisoformat(d["granted_at"]),
    )


def _grants_to_dict(grants: Grants) -> dict:
    return {
        "version": grants.version,
        "user": grants.user,
        "granted_paths": [_granted_path_to_dict(gp) for gp in grants.granted_paths],
        "denied_paths": grants.denied_paths,
        "allow_external_drives": grants.allow_external_drives,
        "allow_network_drives": grants.allow_network_drives,
    }


def _grants_from_dict(data: dict) -> Grants:
    return Grants(
        version=data.get("version", "1.0"),
        user=data.get("user", ""),
        granted_paths=[_granted_path_from_dict(gp) for gp in data.get("granted_paths", [])],
        denied_paths=data.get("denied_paths", []),
        allow_external_drives=data.get("allow_external_drives", False),
        allow_network_drives=data.get("allow_network_drives", False),
    )


def load_grants(base_path: Path = DEFAULT_BASE_PATH) -> Grants:
    """Load grants from *base_path*/grants.json, returning defaults on error."""
    grants_file = base_path / "grants.json"
    if not grants_file.exists():
        return _default_grants()
    try:
        data = json.loads(grants_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("grants.json root is not an object")
        return _grants_from_dict(data)
    except Exception:
        logger.warning("Corrupted or invalid grants.json — returning defaults")
        return _default_grants()


def save_grants(grants: Grants, base_path: Path = DEFAULT_BASE_PATH) -> None:
    """Persist *grants* to *base_path*/grants.json."""
    base_path.mkdir(parents=True, exist_ok=True)
    grants_file = base_path / "grants.json"
    grants_file.write_text(
        json.dumps(_grants_to_dict(grants), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.chmod(grants_file, 0o644)


def add_grant(path: str, access: str, base_path: Path = DEFAULT_BASE_PATH) -> Grants:
    """Add a new granted path and persist."""
    grants = load_grants(base_path)
    grants.granted_paths.append(
        GrantedPath(path=path, access=access, recursive=True, granted_at=datetime.now())
    )
    save_grants(grants, base_path)
    return grants


def remove_grant(path: str, base_path: Path = DEFAULT_BASE_PATH) -> Grants:
    """Remove a granted path and persist."""
    grants = load_grants(base_path)
    grants.granted_paths = [gp for gp in grants.granted_paths if gp.path != path]
    save_grants(grants, base_path)
    return grants


def _resolve_tilde(p: str) -> str:
    """Expand ~ and resolve to a real path."""
    return os.path.realpath(os.path.expanduser(p))


def is_path_denied(path: str, grants: Grants) -> bool:
    """Return True if *path* falls under any denied path."""
    real = os.path.realpath(path)
    for dp in grants.denied_paths:
        resolved = _resolve_tilde(dp)
        if real == resolved or real.startswith(resolved + os.sep):
            return True
    return False


def is_path_granted(path: str, grants: Grants) -> bool:
    """Return True if *path* is granted AND not denied."""
    if is_path_denied(path, grants):
        return False
    real = os.path.realpath(path)
    for gp in grants.granted_paths:
        resolved = _resolve_tilde(gp.path)
        if real == resolved or real.startswith(resolved + os.sep):
            return True
        if not gp.recursive and real == resolved:
            return True
    return False


def get_granted_paths(grants: Grants) -> List[str]:
    """Return resolved path strings for all granted paths."""
    return [_resolve_tilde(gp.path) for gp in grants.granted_paths]


def get_denied_paths(grants: Grants) -> List[str]:
    """Return resolved path strings for all denied paths."""
    return [_resolve_tilde(dp) for dp in grants.denied_paths]


# ---------------------------------------------------------------------------
# WorkspaceManager
# ---------------------------------------------------------------------------

class WorkspaceManager:
    """Creates and manages the ~/.intentos directory tree."""

    def __init__(self, base_path: Path = DEFAULT_BASE_PATH):
        self._base = base_path

    def ensure_workspace(self) -> None:
        """Create the full directory tree (idempotent)."""
        dirs = [
            self._base,
            self._base / "workspace" / "outputs",
            self._base / "workspace" / "temp",
            self._base / "workspace" / "exports",
            self._base / "rag",
            self._base / "logs",
            self._base / "cache" / "thumbs",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def get_workspace_path(self) -> Path:
        return self._base / "workspace"

    def get_outputs_path(self) -> Path:
        return self._base / "workspace" / "outputs"

    def get_logs_path(self) -> Path:
        return self._base / "logs"

    def get_rag_path(self) -> Path:
        return self._base / "rag"


# ---------------------------------------------------------------------------
# IntentOSConfig — top-level bundle
# ---------------------------------------------------------------------------

class IntentOSConfig:
    """Convenience wrapper that bundles workspace, settings, and grants."""

    def __init__(self, base_path: Path = DEFAULT_BASE_PATH):
        self._base = base_path
        self.workspace = WorkspaceManager(base_path)
        self.workspace.ensure_workspace()
        self._first_run = not (base_path / "settings.json").exists()
        self.settings: Settings = load_settings(base_path)
        self.grants: Grants = load_grants(base_path)

    @property
    def is_first_run(self) -> bool:
        return self._first_run

    def save_all(self) -> None:
        """Persist both settings and grants."""
        save_settings(self.settings, self._base)
        save_grants(self.grants, self._base)
