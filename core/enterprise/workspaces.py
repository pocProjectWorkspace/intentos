"""Team Workspaces module (Phase 3B.5).

Provides shared workspaces for SMB/Enterprise teams with role-based access
control, member management, shared paths, and workspace isolation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class WorkspaceRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


# Permissions matrix: role -> set of allowed operations
_ROLE_PERMISSIONS: Dict[WorkspaceRole, set] = {
    WorkspaceRole.ADMIN: {"read", "write", "delete", "manage"},
    WorkspaceRole.MEMBER: {"read", "write"},
    WorkspaceRole.VIEWER: {"read"},
}


@dataclass
class TeamMember:
    user_id: str
    username: str
    role: WorkspaceRole
    joined_at: datetime

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> TeamMember:
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            role=WorkspaceRole(data["role"]),
            joined_at=datetime.fromisoformat(data["joined_at"]),
        )


@dataclass
class Workspace:
    id: str
    name: str
    description: str
    created_at: datetime
    created_by: str
    members: List[TeamMember] = field(default_factory=list)
    shared_paths: List[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "members": [m.to_dict() for m in self.members],
            "shared_paths": self.shared_paths,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Workspace:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data["created_by"],
            members=[TeamMember.from_dict(m) for m in data.get("members", [])],
            shared_paths=data.get("shared_paths", []),
            settings=data.get("settings", {}),
        )


class WorkspaceManager:
    """Manages team workspaces with RBAC."""

    def __init__(self) -> None:
        self._workspaces: Dict[str, Workspace] = {}

    # -- helpers ----------------------------------------------------------

    def _get_member(self, workspace_id: str, user_id: str) -> Optional[TeamMember]:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return None
        for m in ws.members:
            if m.user_id == user_id:
                return m
        return None

    def _require_role(self, workspace_id: str, requester_id: str, required_role: WorkspaceRole) -> None:
        member = self._get_member(workspace_id, requester_id)
        if member is None or member.role != required_role:
            raise PermissionError(
                f"User {requester_id} does not have {required_role.value} access"
            )

    def _require_admin(self, workspace_id: str, requester_id: str) -> None:
        self._require_role(workspace_id, requester_id, WorkspaceRole.ADMIN)

    # -- CRUD -------------------------------------------------------------

    def create_workspace(self, name: str, description: str, creator_user_id: str) -> Workspace:
        ws_id = str(uuid.uuid4())
        now = datetime.utcnow()
        creator = TeamMember(
            user_id=creator_user_id,
            username=creator_user_id,
            role=WorkspaceRole.ADMIN,
            joined_at=now,
        )
        ws = Workspace(
            id=ws_id,
            name=name,
            description=description,
            created_at=now,
            created_by=creator_user_id,
            members=[creator],
            shared_paths=[],
            settings={},
        )
        self._workspaces[ws_id] = ws
        return ws

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    def list_workspaces(self) -> List[Workspace]:
        return list(self._workspaces.values())

    def delete_workspace(self, workspace_id: str, requester_id: str) -> None:
        self._require_admin(workspace_id, requester_id)
        del self._workspaces[workspace_id]

    def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        requester_id: Optional[str] = None,
    ) -> Workspace:
        self._require_admin(workspace_id, requester_id)
        ws = self._workspaces[workspace_id]
        if name is not None:
            ws.name = name
        if description is not None:
            ws.description = description
        return ws

    # -- Member management ------------------------------------------------

    def add_member(
        self,
        workspace_id: str,
        user_id: str,
        username: str,
        role: WorkspaceRole,
        requester_id: str,
    ) -> None:
        self._require_admin(workspace_id, requester_id)
        ws = self._workspaces[workspace_id]
        member = TeamMember(
            user_id=user_id,
            username=username,
            role=role,
            joined_at=datetime.utcnow(),
        )
        ws.members.append(member)

    def remove_member(self, workspace_id: str, user_id: str, requester_id: str) -> None:
        self._require_admin(workspace_id, requester_id)
        ws = self._workspaces[workspace_id]
        # Prevent removing the last admin
        admins = [m for m in ws.members if m.role == WorkspaceRole.ADMIN]
        target = self._get_member(workspace_id, user_id)
        if target and target.role == WorkspaceRole.ADMIN and len(admins) <= 1:
            raise ValueError("Cannot remove the last ADMIN from a workspace")
        ws.members = [m for m in ws.members if m.user_id != user_id]

    def update_role(
        self, workspace_id: str, user_id: str, new_role: WorkspaceRole, requester_id: str
    ) -> None:
        self._require_admin(workspace_id, requester_id)
        member = self._get_member(workspace_id, user_id)
        if member is None:
            raise ValueError(f"User {user_id} is not a member")
        member.role = new_role

    def get_members(self, workspace_id: str) -> List[TeamMember]:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return []
        return list(ws.members)

    def is_member(self, workspace_id: str, user_id: str) -> bool:
        return self._get_member(workspace_id, user_id) is not None

    # -- Shared paths -----------------------------------------------------

    def add_shared_path(self, workspace_id: str, path: str, requester_id: str) -> None:
        member = self._get_member(workspace_id, requester_id)
        if member is None or member.role == WorkspaceRole.VIEWER:
            raise PermissionError("Viewer cannot add shared paths")
        ws = self._workspaces[workspace_id]
        if path not in ws.shared_paths:
            ws.shared_paths.append(path)

    def remove_shared_path(self, workspace_id: str, path: str, requester_id: str) -> None:
        self._require_admin(workspace_id, requester_id)
        ws = self._workspaces[workspace_id]
        if path in ws.shared_paths:
            ws.shared_paths.remove(path)

    def get_shared_paths(self, workspace_id: str) -> List[str]:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return []
        return list(ws.shared_paths)

    # -- Access control ---------------------------------------------------

    def check_access(self, workspace_id: str, user_id: str, operation: str) -> bool:
        member = self._get_member(workspace_id, user_id)
        if member is None:
            return False
        return operation in _ROLE_PERMISSIONS.get(member.role, set())

    # -- Workspace isolation ----------------------------------------------

    def get_workspace_path(self, workspace_id: str) -> Path:
        return Path.home() / ".intentos" / "workspaces" / workspace_id

    # -- Persistence ------------------------------------------------------

    def save(self, path: str) -> None:
        data = {ws_id: ws.to_dict() for ws_id, ws in self._workspaces.items()}
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str) -> None:
        raw = json.loads(Path(path).read_text())
        self._workspaces = {
            ws_id: Workspace.from_dict(ws_data) for ws_id, ws_data in raw.items()
        }
