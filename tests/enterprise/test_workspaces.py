"""Tests for core.enterprise.workspaces — Team Workspaces module (Phase 3B.5)."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from core.enterprise.workspaces import (
    TeamMember,
    Workspace,
    WorkspaceManager,
    WorkspaceRole,
)


# ---------------------------------------------------------------------------
# 1. WorkspaceRole enum
# ---------------------------------------------------------------------------

class TestWorkspaceRole:
    def test_three_roles_exist(self):
        assert WorkspaceRole.ADMIN
        assert WorkspaceRole.MEMBER
        assert WorkspaceRole.VIEWER

    def test_role_values(self):
        assert WorkspaceRole.ADMIN == "admin"
        assert WorkspaceRole.MEMBER == "member"
        assert WorkspaceRole.VIEWER == "viewer"


# ---------------------------------------------------------------------------
# 2-3. TeamMember model
# ---------------------------------------------------------------------------

class TestTeamMember:
    def test_fields(self):
        now = datetime.utcnow()
        m = TeamMember(user_id="u1", username="alice", role=WorkspaceRole.ADMIN, joined_at=now)
        assert m.user_id == "u1"
        assert m.username == "alice"
        assert m.role == WorkspaceRole.ADMIN
        assert m.joined_at == now

    def test_serialization_round_trip(self):
        now = datetime.utcnow()
        m = TeamMember(user_id="u1", username="alice", role=WorkspaceRole.ADMIN, joined_at=now)
        d = m.to_dict()
        m2 = TeamMember.from_dict(d)
        assert m2.user_id == m.user_id
        assert m2.username == m.username
        assert m2.role == m.role
        assert m2.joined_at == m.joined_at


# ---------------------------------------------------------------------------
# 4-5. Workspace model
# ---------------------------------------------------------------------------

class TestWorkspace:
    def test_fields(self):
        now = datetime.utcnow()
        member = TeamMember(user_id="u1", username="alice", role=WorkspaceRole.ADMIN, joined_at=now)
        ws = Workspace(
            id="ws1",
            name="Project X",
            description="desc",
            created_at=now,
            created_by="u1",
            members=[member],
            shared_paths=["/data"],
            settings={"key": "val"},
        )
        assert ws.id == "ws1"
        assert ws.name == "Project X"
        assert ws.description == "desc"
        assert ws.created_at == now
        assert ws.created_by == "u1"
        assert len(ws.members) == 1
        assert ws.shared_paths == ["/data"]
        assert ws.settings == {"key": "val"}

    def test_serialization_round_trip(self):
        now = datetime.utcnow()
        member = TeamMember(user_id="u1", username="alice", role=WorkspaceRole.ADMIN, joined_at=now)
        ws = Workspace(
            id="ws1",
            name="Project X",
            description="desc",
            created_at=now,
            created_by="u1",
            members=[member],
            shared_paths=["/data"],
            settings={"key": "val"},
        )
        d = ws.to_dict()
        ws2 = Workspace.from_dict(d)
        assert ws2.id == ws.id
        assert ws2.name == ws.name
        assert ws2.description == ws.description
        assert ws2.created_at == ws.created_at
        assert ws2.created_by == ws.created_by
        assert len(ws2.members) == 1
        assert ws2.members[0].user_id == "u1"
        assert ws2.shared_paths == ws.shared_paths
        assert ws2.settings == ws.settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    return WorkspaceManager()


@pytest.fixture
def workspace_with_members(mgr):
    """Create a workspace and add a MEMBER and a VIEWER."""
    ws = mgr.create_workspace("Team A", "desc", "creator1")
    mgr.add_member(ws.id, "member1", "bob", WorkspaceRole.MEMBER, "creator1")
    mgr.add_member(ws.id, "viewer1", "carol", WorkspaceRole.VIEWER, "creator1")
    return ws


# ---------------------------------------------------------------------------
# 6-12. CRUD
# ---------------------------------------------------------------------------

class TestWorkspaceCRUD:
    def test_create_workspace(self, mgr):
        ws = mgr.create_workspace("My WS", "A workspace", "user1")
        assert ws.name == "My WS"
        assert ws.description == "A workspace"
        assert ws.created_by == "user1"
        assert ws.id  # non-empty

    def test_creator_added_as_admin(self, mgr):
        ws = mgr.create_workspace("WS", "d", "user1")
        assert len(ws.members) == 1
        assert ws.members[0].user_id == "user1"
        assert ws.members[0].role == WorkspaceRole.ADMIN

    def test_get_workspace(self, mgr):
        ws = mgr.create_workspace("WS", "d", "user1")
        fetched = mgr.get_workspace(ws.id)
        assert fetched is not None
        assert fetched.id == ws.id

    def test_get_workspace_not_found(self, mgr):
        assert mgr.get_workspace("nonexistent") is None

    def test_list_workspaces(self, mgr):
        mgr.create_workspace("A", "d", "u1")
        mgr.create_workspace("B", "d", "u2")
        assert len(mgr.list_workspaces()) == 2

    def test_delete_workspace_admin(self, mgr):
        ws = mgr.create_workspace("WS", "d", "user1")
        mgr.delete_workspace(ws.id, "user1")
        assert mgr.get_workspace(ws.id) is None

    def test_delete_workspace_non_admin_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        with pytest.raises(PermissionError):
            mgr.delete_workspace(ws.id, "member1")

    def test_update_workspace_admin(self, mgr):
        ws = mgr.create_workspace("Old", "old desc", "user1")
        mgr.update_workspace(ws.id, name="New", description="new desc", requester_id="user1")
        updated = mgr.get_workspace(ws.id)
        assert updated.name == "New"
        assert updated.description == "new desc"

    def test_update_workspace_non_admin_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        with pytest.raises(PermissionError):
            mgr.update_workspace(ws.id, name="X", requester_id="member1")


# ---------------------------------------------------------------------------
# 13-17. Member management
# ---------------------------------------------------------------------------

class TestMemberManagement:
    def test_add_member(self, mgr):
        ws = mgr.create_workspace("WS", "d", "admin1")
        mgr.add_member(ws.id, "u2", "bob", WorkspaceRole.MEMBER, "admin1")
        members = mgr.get_members(ws.id)
        assert len(members) == 2

    def test_add_member_non_admin_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        with pytest.raises(PermissionError):
            mgr.add_member(ws.id, "u99", "dan", WorkspaceRole.MEMBER, "member1")

    def test_remove_member(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.remove_member(ws.id, "member1", "creator1")
        assert not mgr.is_member(ws.id, "member1")

    def test_remove_member_non_admin_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        with pytest.raises(PermissionError):
            mgr.remove_member(ws.id, "viewer1", "member1")

    def test_cannot_remove_last_admin(self, mgr):
        ws = mgr.create_workspace("WS", "d", "admin1")
        with pytest.raises(ValueError):
            mgr.remove_member(ws.id, "admin1", "admin1")

    def test_update_role(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.update_role(ws.id, "member1", WorkspaceRole.ADMIN, "creator1")
        members = mgr.get_members(ws.id)
        member = [m for m in members if m.user_id == "member1"][0]
        assert member.role == WorkspaceRole.ADMIN

    def test_update_role_non_admin_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        with pytest.raises(PermissionError):
            mgr.update_role(ws.id, "viewer1", WorkspaceRole.MEMBER, "member1")

    def test_get_members(self, mgr, workspace_with_members):
        ws = workspace_with_members
        members = mgr.get_members(ws.id)
        assert len(members) == 3

    def test_is_member_true(self, mgr, workspace_with_members):
        ws = workspace_with_members
        assert mgr.is_member(ws.id, "creator1")

    def test_is_member_false(self, mgr, workspace_with_members):
        ws = workspace_with_members
        assert not mgr.is_member(ws.id, "stranger")


# ---------------------------------------------------------------------------
# 18-21. Shared paths
# ---------------------------------------------------------------------------

class TestSharedPaths:
    def test_add_shared_path_admin(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.add_shared_path(ws.id, "/new/path", "creator1")
        assert "/new/path" in mgr.get_shared_paths(ws.id)

    def test_add_shared_path_member(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.add_shared_path(ws.id, "/member/path", "member1")
        assert "/member/path" in mgr.get_shared_paths(ws.id)

    def test_add_shared_path_viewer_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        with pytest.raises(PermissionError):
            mgr.add_shared_path(ws.id, "/viewer/path", "viewer1")

    def test_remove_shared_path_admin(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.add_shared_path(ws.id, "/rem", "creator1")
        mgr.remove_shared_path(ws.id, "/rem", "creator1")
        assert "/rem" not in mgr.get_shared_paths(ws.id)

    def test_remove_shared_path_non_admin_raises(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.add_shared_path(ws.id, "/x", "creator1")
        with pytest.raises(PermissionError):
            mgr.remove_shared_path(ws.id, "/x", "member1")

    def test_get_shared_paths(self, mgr):
        ws = mgr.create_workspace("WS", "d", "u1")
        mgr.add_shared_path(ws.id, "/a", "u1")
        mgr.add_shared_path(ws.id, "/b", "u1")
        paths = mgr.get_shared_paths(ws.id)
        assert set(paths) == {"/a", "/b"}


# ---------------------------------------------------------------------------
# 22-26. Access control
# ---------------------------------------------------------------------------

class TestAccessControl:
    def test_admin_full_access(self, mgr, workspace_with_members):
        ws = workspace_with_members
        for op in ("read", "write", "delete", "manage"):
            assert mgr.check_access(ws.id, "creator1", op)

    def test_member_read_write(self, mgr, workspace_with_members):
        ws = workspace_with_members
        assert mgr.check_access(ws.id, "member1", "read")
        assert mgr.check_access(ws.id, "member1", "write")
        assert not mgr.check_access(ws.id, "member1", "delete")
        assert not mgr.check_access(ws.id, "member1", "manage")

    def test_viewer_read_only(self, mgr, workspace_with_members):
        ws = workspace_with_members
        assert mgr.check_access(ws.id, "viewer1", "read")
        assert not mgr.check_access(ws.id, "viewer1", "write")
        assert not mgr.check_access(ws.id, "viewer1", "delete")
        assert not mgr.check_access(ws.id, "viewer1", "manage")

    def test_non_member_no_access(self, mgr, workspace_with_members):
        ws = workspace_with_members
        for op in ("read", "write", "delete", "manage"):
            assert not mgr.check_access(ws.id, "stranger", op)


# ---------------------------------------------------------------------------
# 27-29. Workspace isolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_workspace_path(self, mgr):
        ws = mgr.create_workspace("WS", "d", "u1")
        expected = Path.home() / ".intentos" / "workspaces" / ws.id
        assert mgr.get_workspace_path(ws.id) == expected

    def test_outputs_directory(self, mgr):
        ws = mgr.create_workspace("WS", "d", "u1")
        wp = mgr.get_workspace_path(ws.id)
        assert wp / "outputs" == Path.home() / ".intentos" / "workspaces" / ws.id / "outputs"


# ---------------------------------------------------------------------------
# 30-31. Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.add_shared_path(ws.id, "/shared", "creator1")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        mgr.save(path)

        mgr2 = WorkspaceManager()
        mgr2.load(path)

        loaded = mgr2.get_workspace(ws.id)
        assert loaded is not None
        assert loaded.name == ws.name
        assert len(mgr2.get_members(ws.id)) == 3
        assert "/shared" in mgr2.get_shared_paths(ws.id)
        Path(path).unlink()

    def test_round_trip_preserves_all_data(self, mgr):
        ws = mgr.create_workspace("RT", "round-trip", "u1")
        mgr.add_member(ws.id, "u2", "bob", WorkspaceRole.MEMBER, "u1")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        mgr.save(path)
        mgr2 = WorkspaceManager()
        mgr2.load(path)

        orig = mgr.get_workspace(ws.id)
        loaded = mgr2.get_workspace(ws.id)
        assert orig.to_dict() == loaded.to_dict()
        Path(path).unlink()


# ---------------------------------------------------------------------------
# 32-35. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_duplicate_workspace_names_allowed(self, mgr):
        ws1 = mgr.create_workspace("Same", "d", "u1")
        ws2 = mgr.create_workspace("Same", "d", "u2")
        assert ws1.id != ws2.id
        assert len(mgr.list_workspaces()) == 2

    def test_empty_workspace_valid(self, mgr):
        ws = mgr.create_workspace("Solo", "d", "u1")
        assert len(ws.members) == 1  # only creator

    def test_delete_workspace_with_multiple_members(self, mgr, workspace_with_members):
        ws = workspace_with_members
        mgr.delete_workspace(ws.id, "creator1")
        assert mgr.get_workspace(ws.id) is None

    def test_user_in_multiple_workspaces(self, mgr):
        ws1 = mgr.create_workspace("A", "d", "shared_user")
        ws2 = mgr.create_workspace("B", "d", "shared_user")
        assert mgr.is_member(ws1.id, "shared_user")
        assert mgr.is_member(ws2.id, "shared_user")
        mgr.delete_workspace(ws1.id, "shared_user")
        assert mgr.get_workspace(ws1.id) is None
        assert mgr.is_member(ws2.id, "shared_user")
