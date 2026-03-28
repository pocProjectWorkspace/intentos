"""
Tests for IntentOS Sandbox Policies (Phase 2A.5).

Covers SandboxPolicy enum, SandboxManager, path enforcement,
path traversal prevention, denied paths, resource limits,
network policy, and edge cases.
"""

import os
import tempfile
import pytest

from core.security.sandbox import (
    SandboxPolicy,
    FileOp,
    SandboxConfig,
    OperationResult,
    Sandbox,
    SandboxManager,
    DEFAULT_DENIED_PATHS,
)
from core.security.exceptions import SecurityError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return str(ws)


@pytest.fixture
def granted_dir(tmp_path):
    """Create a temporary granted directory outside workspace."""
    d = tmp_path / "granted"
    d.mkdir()
    (d / "file.txt").write_text("hello")
    return str(d)


@pytest.fixture
def outside_dir(tmp_path):
    """Create a directory that is NOT in granted_paths."""
    d = tmp_path / "outside"
    d.mkdir()
    (d / "secret.txt").write_text("secret")
    return str(d)


# ---------------------------------------------------------------------------
# 1. SandboxPolicy enum
# ---------------------------------------------------------------------------

class TestSandboxPolicyEnum:
    def test_three_tiers_exist(self):
        """Test 1: Three tiers exist — READ_ONLY, WORKSPACE_WRITE, FULL_ACCESS."""
        assert SandboxPolicy.READ_ONLY is not None
        assert SandboxPolicy.WORKSPACE_WRITE is not None
        assert SandboxPolicy.FULL_ACCESS is not None
        assert len(SandboxPolicy) == 3


# ---------------------------------------------------------------------------
# 2-12. Path enforcement
# ---------------------------------------------------------------------------

class TestReadOnlyPolicy:
    def test_allows_reading_in_granted_paths(self, workspace, granted_dir):
        """Test 2: ReadOnly allows reading files inside granted_paths."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.READ, os.path.join(granted_dir, "file.txt"))
        assert result.allowed is True

    def test_blocks_writing(self, workspace, granted_dir):
        """Test 3: ReadOnly blocks writing to any path including workspace."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir, workspace],
            workspace=workspace,
        )
        result = sb.check(FileOp.WRITE, os.path.join(workspace, "out.txt"))
        assert result.allowed is False

    def test_blocks_deleting(self, workspace, granted_dir):
        """Test 4: ReadOnly blocks deleting files."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.DELETE, os.path.join(granted_dir, "file.txt"))
        assert result.allowed is False


class TestWorkspaceWritePolicy:
    def test_allows_reading_granted(self, workspace, granted_dir):
        """Test 5: WorkspaceWrite allows reading from granted_paths."""
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.READ, os.path.join(granted_dir, "file.txt"))
        assert result.allowed is True

    def test_allows_writing_to_workspace(self, workspace, granted_dir):
        """Test 6: WorkspaceWrite allows writing to workspace directory."""
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.WRITE, os.path.join(workspace, "out.txt"))
        assert result.allowed is True

    def test_blocks_writing_outside_workspace(self, workspace, granted_dir):
        """Test 7: WorkspaceWrite blocks writing outside workspace."""
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.WRITE, os.path.join(granted_dir, "hack.txt"))
        assert result.allowed is False

    def test_blocks_deleting_outside_workspace(self, workspace, granted_dir):
        """Test 8: WorkspaceWrite blocks deleting outside workspace."""
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.DELETE, os.path.join(granted_dir, "file.txt"))
        assert result.allowed is False

    def test_allows_creating_folders_in_workspace(self, workspace, granted_dir):
        """Test 9: WorkspaceWrite allows creating folders in workspace."""
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.CREATE_DIR, os.path.join(workspace, "subdir"))
        assert result.allowed is True


class TestFullAccessPolicy:
    def test_allows_reading_granted(self, workspace, granted_dir):
        """Test 10: FullAccess allows reading anywhere in granted_paths."""
        config = SandboxConfig(explicit_full_access=True)
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        result = sb.check(FileOp.READ, os.path.join(granted_dir, "file.txt"))
        assert result.allowed is True

    def test_allows_writing_granted(self, workspace, granted_dir):
        """Test 11: FullAccess allows writing anywhere in granted_paths."""
        config = SandboxConfig(explicit_full_access=True)
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        result = sb.check(FileOp.WRITE, os.path.join(granted_dir, "new.txt"))
        assert result.allowed is True

    def test_allows_deleting_granted(self, workspace, granted_dir):
        """Test 12: FullAccess allows deleting in granted_paths."""
        config = SandboxConfig(explicit_full_access=True)
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        result = sb.check(FileOp.DELETE, os.path.join(granted_dir, "file.txt"))
        assert result.allowed is True


# ---------------------------------------------------------------------------
# 13-15. Double opt-in for FullAccess
# ---------------------------------------------------------------------------

class TestDoubleOptIn:
    def test_full_access_requires_both_policy_and_flag(self, workspace, granted_dir):
        """Test 13: FullAccess requires policy=FULL_ACCESS AND explicit_full_access=True."""
        config = SandboxConfig(explicit_full_access=True)
        mgr = SandboxManager()
        sb = mgr.create_sandbox(
            agent_name="agent-1",
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        assert sb.policy == SandboxPolicy.FULL_ACCESS

    def test_full_access_without_flag_raises(self, workspace, granted_dir):
        """Test 14: FullAccess without explicit flag raises SecurityError."""
        config = SandboxConfig(explicit_full_access=False)
        mgr = SandboxManager()
        with pytest.raises(SecurityError):
            mgr.create_sandbox(
                agent_name="agent-1",
                policy=SandboxPolicy.FULL_ACCESS,
                granted_paths=[granted_dir],
                workspace=workspace,
                config=config,
            )

    def test_readonly_does_not_require_flag(self, workspace, granted_dir):
        """Test 15a: ReadOnly does NOT require the explicit flag."""
        mgr = SandboxManager()
        sb = mgr.create_sandbox(
            agent_name="agent-1",
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        assert sb.policy == SandboxPolicy.READ_ONLY

    def test_workspace_write_does_not_require_flag(self, workspace, granted_dir):
        """Test 15b: WorkspaceWrite does NOT require the explicit flag."""
        mgr = SandboxManager()
        sb = mgr.create_sandbox(
            agent_name="agent-1",
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        assert sb.policy == SandboxPolicy.WORKSPACE_WRITE


# ---------------------------------------------------------------------------
# 16-18. Path traversal prevention
# ---------------------------------------------------------------------------

class TestPathTraversalPrevention:
    def test_symlink_escape_blocked(self, workspace, granted_dir, outside_dir):
        """Test 16: Symlink resolving outside granted_paths is blocked."""
        link_path = os.path.join(granted_dir, "sneaky_link")
        os.symlink(outside_dir, link_path)

        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        target = os.path.join(link_path, "secret.txt")
        result = sb.check(FileOp.READ, target)
        assert result.allowed is False
        assert "outside" in result.reason.lower() or "denied" in result.reason.lower() or "granted" in result.reason.lower()

    def test_dotdot_traversal_blocked(self, workspace, granted_dir):
        """Test 17: '..' traversal escaping granted_paths is blocked."""
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        evil_path = os.path.join(granted_dir, "..", "..", "..", "etc", "passwd")
        result = sb.check(FileOp.READ, evil_path)
        assert result.allowed is False

    def test_absolute_path_must_be_within_granted(self, workspace, granted_dir, outside_dir):
        """Test 18: Absolute path outside granted_paths is blocked."""
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        result = sb.check(FileOp.READ, os.path.join(outside_dir, "secret.txt"))
        assert result.allowed is False


# ---------------------------------------------------------------------------
# 19-22. Denied paths
# ---------------------------------------------------------------------------

class TestDeniedPaths:
    def test_denied_paths_always_blocked(self, workspace, tmp_path):
        """Test 19: Operations on denied_paths are always blocked."""
        denied = str(tmp_path / "forbidden")
        os.makedirs(denied, exist_ok=True)

        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[str(tmp_path)],
            workspace=workspace,
            denied_paths=[denied],
            config=SandboxConfig(explicit_full_access=True),
        )
        result = sb.check(FileOp.READ, os.path.join(denied, "data.txt"))
        assert result.allowed is False

    def test_ssh_always_denied(self, workspace, tmp_path):
        """Test 20: ~/.ssh is always denied."""
        home = os.path.expanduser("~")
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[home],
            workspace=workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        result = sb.check(FileOp.READ, os.path.join(home, ".ssh", "id_rsa"))
        assert result.allowed is False

    def test_aws_always_denied(self, workspace, tmp_path):
        """Test 21: ~/.aws is always denied."""
        home = os.path.expanduser("~")
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[home],
            workspace=workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        result = sb.check(FileOp.READ, os.path.join(home, ".aws", "credentials"))
        assert result.allowed is False

    def test_denied_takes_priority_over_granted(self, workspace, tmp_path):
        """Test 22: Denied paths take priority over granted paths."""
        sensitive = str(tmp_path / "sensitive")
        os.makedirs(sensitive, exist_ok=True)

        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[str(tmp_path)],
            workspace=workspace,
            denied_paths=[sensitive],
            config=SandboxConfig(explicit_full_access=True),
        )
        # tmp_path is granted, but sensitive is denied
        result_granted = sb.check(FileOp.READ, os.path.join(str(tmp_path), "ok.txt"))
        result_denied = sb.check(FileOp.READ, os.path.join(sensitive, "nope.txt"))
        assert result_granted.allowed is True
        assert result_denied.allowed is False


# ---------------------------------------------------------------------------
# 23-24. Operation types
# ---------------------------------------------------------------------------

class TestOperationTypes:
    def test_fileop_enum_members(self):
        """Test 23: FileOp enum has READ, WRITE, DELETE, CREATE_DIR, MOVE, COPY, EXECUTE."""
        assert FileOp.READ is not None
        assert FileOp.WRITE is not None
        assert FileOp.DELETE is not None
        assert FileOp.CREATE_DIR is not None
        assert FileOp.MOVE is not None
        assert FileOp.COPY is not None
        assert FileOp.EXECUTE is not None
        assert len(FileOp) == 7

    def test_check_operation_returns_operation_result(self, workspace, granted_dir):
        """Test 24: check_operation() returns OperationResult with allowed and reason."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.READ, os.path.join(granted_dir, "file.txt"))
        assert isinstance(result, OperationResult)
        assert isinstance(result.allowed, bool)
        assert isinstance(result.reason, str)


# ---------------------------------------------------------------------------
# 25-26. Resource limits
# ---------------------------------------------------------------------------

class TestResourceLimits:
    def test_default_limits(self):
        """Test 25: SandboxConfig defaults — max_memory_mb=2048, max_cpu_seconds=120, max_output_bytes=65536."""
        config = SandboxConfig()
        assert config.max_memory_mb == 2048
        assert config.max_cpu_seconds == 120
        assert config.max_output_bytes == 65536

    def test_limits_accessible_from_sandbox(self, workspace, granted_dir):
        """Test 26: Limits accessible from sandbox instance."""
        config = SandboxConfig(max_memory_mb=512, max_cpu_seconds=60, max_output_bytes=1024)
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        assert sb.config.max_memory_mb == 512
        assert sb.config.max_cpu_seconds == 60
        assert sb.config.max_output_bytes == 1024


# ---------------------------------------------------------------------------
# 27-29. Network policy
# ---------------------------------------------------------------------------

class TestNetworkPolicy:
    def test_readonly_network_blocked(self, workspace, granted_dir):
        """Test 27: ReadOnly — network blocked."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        assert sb.network_allowed is False

    def test_workspace_write_network_default_blocked(self, workspace, granted_dir):
        """Test 28a: WorkspaceWrite — network blocked by default."""
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        assert sb.network_allowed is False

    def test_workspace_write_network_allowed_via_config(self, workspace, granted_dir):
        """Test 28b: WorkspaceWrite — network allowed if network_allowed=True in config."""
        config = SandboxConfig(network_allowed=True)
        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        assert sb.network_allowed is True

    def test_full_access_network_allowed(self, workspace, granted_dir):
        """Test 29: FullAccess — network allowed."""
        config = SandboxConfig(explicit_full_access=True)
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[granted_dir],
            workspace=workspace,
            config=config,
        )
        assert sb.network_allowed is True


# ---------------------------------------------------------------------------
# 30-32. Sandbox creation
# ---------------------------------------------------------------------------

class TestSandboxCreation:
    def test_create_sandbox_returns_sandbox(self, workspace, granted_dir):
        """Test 30: create_sandbox() returns Sandbox with policy, granted_paths, workspace, denied_paths, config."""
        mgr = SandboxManager()
        sb = mgr.create_sandbox(
            agent_name="agent-1",
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        assert isinstance(sb, Sandbox)
        assert sb.policy == SandboxPolicy.READ_ONLY
        assert granted_dir in sb.granted_paths
        assert sb.workspace == os.path.realpath(workspace)
        assert sb.config is not None

    def test_check_is_convenience_method(self, workspace, granted_dir):
        """Test 31: Sandbox.check() is a convenience that calls check_operation()."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        result = sb.check(FileOp.READ, os.path.join(granted_dir, "file.txt"))
        assert isinstance(result, OperationResult)

    def test_multiple_sandboxes_coexist(self, workspace, granted_dir):
        """Test 32: Multiple sandboxes with different policies can coexist."""
        mgr = SandboxManager()
        sb1 = mgr.create_sandbox("a1", SandboxPolicy.READ_ONLY, [granted_dir], workspace)
        sb2 = mgr.create_sandbox("a2", SandboxPolicy.WORKSPACE_WRITE, [granted_dir], workspace)
        sb3 = mgr.create_sandbox(
            "a3", SandboxPolicy.FULL_ACCESS, [granted_dir], workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        assert sb1.policy == SandboxPolicy.READ_ONLY
        assert sb2.policy == SandboxPolicy.WORKSPACE_WRITE
        assert sb3.policy == SandboxPolicy.FULL_ACCESS


# ---------------------------------------------------------------------------
# 33-35. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_granted_paths_blocks_all(self, workspace):
        """Test 33: Empty granted_paths — all read/write blocked."""
        sb = Sandbox(
            policy=SandboxPolicy.FULL_ACCESS,
            granted_paths=[],
            workspace=workspace,
            config=SandboxConfig(explicit_full_access=True),
        )
        result = sb.check(FileOp.READ, "/some/random/file.txt")
        assert result.allowed is False

    def test_workspace_implicitly_granted_for_write(self, workspace, tmp_path):
        """Test 34: Workspace not in granted_paths — workspace writes still work."""
        other = str(tmp_path / "other")
        os.makedirs(other, exist_ok=True)

        sb = Sandbox(
            policy=SandboxPolicy.WORKSPACE_WRITE,
            granted_paths=[other],
            workspace=workspace,
        )
        result = sb.check(FileOp.WRITE, os.path.join(workspace, "out.txt"))
        assert result.allowed is True

    def test_check_none_path_raises(self, workspace, granted_dir):
        """Test 35: check_operation on None path raises ValueError."""
        sb = Sandbox(
            policy=SandboxPolicy.READ_ONLY,
            granted_paths=[granted_dir],
            workspace=workspace,
        )
        with pytest.raises(ValueError):
            sb.check(FileOp.READ, None)
