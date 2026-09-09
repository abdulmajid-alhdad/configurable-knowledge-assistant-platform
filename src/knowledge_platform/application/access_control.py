"""Application ports and stable failures for scoped access control."""

from typing import Protocol
from uuid import UUID

from knowledge_platform.modules.access_control.domain import (
    AuthenticatedUser,
    Permission,
)


class AccessDenied(RuntimeError):
    """The actor lacks the required canonical permission and scope."""


class AccessConflict(RuntimeError):
    """A safe access-control invariant rejected a requested mutation."""


class AccessNotFound(RuntimeError):
    """The requested scoped access-control resource is unavailable."""


class AccessControlPort(Protocol):
    """Authority boundary consumed by application and delivery services."""

    def sync_profile(self, user: AuthenticatedUser) -> None: ...

    def discover_workspaces(self, user_id: UUID) -> list[dict[str, object]]: ...

    def list_workspaces(self, actor: UUID) -> list[dict[str, object]]: ...

    def permissions(self, user_id: UUID, workspace_id: UUID) -> frozenset[str]: ...

    def require(
        self, user_id: UUID, workspace_id: UUID, permission: Permission
    ) -> None: ...

    def system_permissions(self, user_id: UUID) -> frozenset[str]: ...

    def require_system(self, user_id: UUID, permission: Permission) -> None: ...

    def list_system_access(self, actor: UUID) -> list[dict[str, object]]: ...

    def list_users(self, actor: UUID) -> list[dict[str, object]]: ...

    def list_system_roles(self, actor: UUID) -> list[dict[str, object]]: ...

    def create_system_role(
        self, actor: UUID, name: str, permissions: list[str]
    ) -> UUID: ...

    def update_system_role(
        self, actor: UUID, role_id: UUID, name: str, permissions: list[str]
    ) -> None: ...

    def delete_system_role(self, actor: UUID, role_id: UUID) -> None: ...

    def assign_system_access(
        self, actor: UUID, user_id: UUID, role_id: UUID
    ) -> None: ...

    def revoke_system_access(
        self, actor: UUID, user_id: UUID, role_id: UUID
    ) -> None: ...

    def create_workspace(
        self,
        user_id: UUID,
        name: str,
        *,
        ai_execution_enabled: bool = True,
    ) -> dict[str, object]: ...

    def update_workspace(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        name: str,
        operational_status: str,
        ai_execution_enabled: bool,
    ) -> dict[str, object]: ...

    def create_role(
        self, actor: UUID, workspace_id: UUID, name: str, permissions: list[str]
    ) -> UUID: ...

    def update_role(
        self,
        actor: UUID,
        workspace_id: UUID,
        role_id: UUID,
        name: str,
        permissions: list[str],
    ) -> None: ...

    def delete_role(self, actor: UUID, workspace_id: UUID, role_id: UUID) -> None: ...

    def list_roles(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def list_members(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def change_member_role(
        self, actor: UUID, workspace_id: UUID, member: UUID, role: UUID
    ) -> None: ...

    def remove_member(self, actor: UUID, workspace_id: UUID, member: UUID) -> None: ...

    def list_teams(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def save_team(
        self,
        actor: UUID,
        workspace_id: UUID,
        name: str,
        description: str | None,
        team_id: UUID | None = None,
    ) -> UUID: ...

    def delete_team(self, actor: UUID, workspace_id: UUID, team_id: UUID) -> None: ...

    def set_team_member(
        self,
        actor: UUID,
        workspace_id: UUID,
        team_id: UUID,
        member_id: UUID,
        present: bool,
    ) -> None: ...

    def list_invitations(
        self, actor: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def revoke_invitation(
        self, actor: UUID, workspace_id: UUID, invitation_id: UUID
    ) -> None: ...
