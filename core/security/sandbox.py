"""
IntentOS Sandbox Policies (Phase 2A.5).

Enforces filesystem and network access boundaries for agent execution.
Enterprise security critical — all path operations are resolved to
real paths before access checks to prevent symlink and traversal attacks.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from core.security.exceptions import SecurityError


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SandboxPolicy(Enum):
    """Three-tier sandbox policy."""
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    FULL_ACCESS = "full_access"


class FileOp(Enum):
    """Filesystem operation types."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    CREATE_DIR = "create_dir"
    MOVE = "move"
    COPY = "copy"
    EXECUTE = "execute"


# Operations that mutate the filesystem
_WRITE_OPS = {FileOp.WRITE, FileOp.DELETE, FileOp.CREATE_DIR, FileOp.MOVE, FileOp.COPY, FileOp.EXECUTE}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SandboxConfig:
    """Resource limits and flags for a sandbox."""
    max_memory_mb: int = 2048
    max_cpu_seconds: int = 120
    max_output_bytes: int = 65536
    network_allowed: bool = False
    explicit_full_access: bool = False


@dataclass
class OperationResult:
    """Result of a sandbox access check."""
    allowed: bool
    reason: str
    policy: SandboxPolicy


# ---------------------------------------------------------------------------
# Default denied paths (always blocked regardless of policy)
# ---------------------------------------------------------------------------

DEFAULT_DENIED_PATHS: List[str] = [
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.env",
    "~/.config/gcloud",
]


def _expand_denied_paths(paths: List[str]) -> List[str]:
    """Expand ~ in denied paths and resolve to real absolute paths."""
    return [os.path.realpath(os.path.expanduser(p)) for p in paths]


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class Sandbox:
    """Enforces filesystem and network boundaries for a single agent."""

    def __init__(
        self,
        policy: SandboxPolicy,
        granted_paths: List[str],
        workspace: str,
        denied_paths: Optional[List[str]] = None,
        config: Optional[SandboxConfig] = None,
    ):
        self.policy = policy
        self.config = config or SandboxConfig()
        self.workspace = os.path.realpath(workspace)

        # Resolve granted paths to real absolute paths
        self.granted_paths = [os.path.realpath(p) for p in granted_paths]

        # Merge user-supplied denied paths with defaults
        user_denied = denied_paths or []
        all_denied = [os.path.realpath(os.path.expanduser(d)) for d in user_denied]
        all_denied.extend(_expand_denied_paths(DEFAULT_DENIED_PATHS))
        self.denied_paths = all_denied

    # -- public API ---------------------------------------------------------

    @property
    def network_allowed(self) -> bool:
        """Whether network access is permitted under this sandbox."""
        if self.policy == SandboxPolicy.FULL_ACCESS:
            return True
        if self.policy == SandboxPolicy.WORKSPACE_WRITE:
            return self.config.network_allowed
        return False  # READ_ONLY

    def check(self, operation: FileOp, path: str) -> OperationResult:
        """Convenience method — delegates to check_operation."""
        return self.check_operation(operation, path)

    def check_operation(self, operation: FileOp, path: str) -> OperationResult:
        """Core access-control check. Returns OperationResult."""
        if path is None:
            raise ValueError("path must not be None")

        resolved = os.path.realpath(os.path.expanduser(path))

        # 1. Denied paths take absolute priority
        if self._is_path_denied(resolved):
            return OperationResult(
                allowed=False,
                reason=f"Path is in denied list: {resolved}",
                policy=self.policy,
            )

        # 2. Determine whether path is in granted area or workspace
        in_granted = self._is_path_granted(resolved)
        in_workspace = self._is_workspace(resolved)

        # 3. Policy-specific checks
        if self.policy == SandboxPolicy.READ_ONLY:
            return self._check_read_only(operation, resolved, in_granted, in_workspace)
        elif self.policy == SandboxPolicy.WORKSPACE_WRITE:
            return self._check_workspace_write(operation, resolved, in_granted, in_workspace)
        elif self.policy == SandboxPolicy.FULL_ACCESS:
            return self._check_full_access(operation, resolved, in_granted, in_workspace)

        return OperationResult(allowed=False, reason="Unknown policy", policy=self.policy)

    # -- private helpers ----------------------------------------------------

    def _is_path_granted(self, resolved: str) -> bool:
        """True if resolved path starts with any granted_path."""
        return any(
            resolved == gp or resolved.startswith(gp + os.sep)
            for gp in self.granted_paths
        )

    def _is_path_denied(self, resolved: str) -> bool:
        """True if resolved path starts with any denied_path."""
        return any(
            resolved == dp or resolved.startswith(dp + os.sep)
            for dp in self.denied_paths
        )

    def _is_workspace(self, resolved: str) -> bool:
        """True if resolved path starts with the workspace."""
        return resolved == self.workspace or resolved.startswith(self.workspace + os.sep)

    # -- policy implementations ---------------------------------------------

    def _check_read_only(self, op: FileOp, resolved: str, in_granted: bool, in_workspace: bool) -> OperationResult:
        if op in _WRITE_OPS:
            return OperationResult(False, f"READ_ONLY policy denies {op.value} operations", self.policy)
        # READ
        if in_granted or in_workspace:
            return OperationResult(True, "Read allowed within granted/workspace paths", self.policy)
        return OperationResult(False, "Path is not within granted paths", self.policy)

    def _check_workspace_write(self, op: FileOp, resolved: str, in_granted: bool, in_workspace: bool) -> OperationResult:
        if op == FileOp.READ:
            if in_granted or in_workspace:
                return OperationResult(True, "Read allowed within granted/workspace paths", self.policy)
            return OperationResult(False, "Path is not within granted paths", self.policy)
        # Write ops
        if op in _WRITE_OPS:
            if in_workspace:
                return OperationResult(True, f"{op.value} allowed in workspace", self.policy)
            return OperationResult(False, f"WORKSPACE_WRITE policy denies {op.value} outside workspace", self.policy)
        return OperationResult(False, "Unknown operation", self.policy)

    def _check_full_access(self, op: FileOp, resolved: str, in_granted: bool, in_workspace: bool) -> OperationResult:
        if in_granted or in_workspace:
            return OperationResult(True, f"{op.value} allowed under FULL_ACCESS in granted/workspace paths", self.policy)
        return OperationResult(False, "Path is not within granted paths", self.policy)


# ---------------------------------------------------------------------------
# SandboxManager
# ---------------------------------------------------------------------------

class SandboxManager:
    """Factory for creating sandboxes with policy validation."""

    def create_sandbox(
        self,
        agent_name: str,
        policy: SandboxPolicy,
        granted_paths: List[str],
        workspace: str,
        config: Optional[SandboxConfig] = None,
        manifest: Optional[dict] = None,
    ) -> Sandbox:
        """Create a new Sandbox, enforcing double opt-in for FULL_ACCESS."""
        cfg = config or SandboxConfig()

        # Double opt-in: FULL_ACCESS requires explicit flag
        if policy == SandboxPolicy.FULL_ACCESS and not cfg.explicit_full_access:
            raise SecurityError(
                f"FULL_ACCESS policy for agent '{agent_name}' requires "
                "explicit_full_access=True in SandboxConfig"
            )

        # Merge manifest network_allowed into config if present
        if manifest and manifest.get("network_allowed"):
            cfg.network_allowed = True

        return Sandbox(
            policy=policy,
            granted_paths=granted_paths,
            workspace=workspace,
            config=cfg,
        )
