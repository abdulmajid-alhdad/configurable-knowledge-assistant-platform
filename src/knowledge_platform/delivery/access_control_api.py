"""Authenticated Stage 7A workspace access-administration API."""

from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.access_control import (
    AccessConflict,
    AccessControlPort,
    AccessNotFound,
)
from knowledge_platform.modules.access_control.domain import (
    PERMISSION_CATALOG,
    Permission,
)


class NamedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class RoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    permissions: list[str]


class RoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: UUID


class WorkspaceAdministrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    operational_status: Literal["ACTIVE", "SUSPENDED"]
    ai_execution_enabled: bool


class SystemAccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role_id: UUID


def _permission_catalogue() -> list[dict[str, object]]:
    definitions = sorted(
        PERMISSION_CATALOG.values(), key=lambda item: item.permission.value
    )
    return [
        {
            "code": definition.permission.value,
            "scope": definition.scope.value,
            "resource": definition.resource,
            "action": definition.action,
            "active": definition.active,
            "delegable": definition.delegable,
        }
        for definition in definitions
    ]


def create_access_router(access: AccessControlPort, *, system: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api/system" if system else "/api")

    def user(request: Request) -> UUID:
        return cast(UUID, request.state.user.id)

    if system:

        @router.get("/me/permissions")
        def system_permissions(request: Request) -> list[str]:
            return sorted(access.system_permissions(user(request)))

        @router.get("/workspaces")
        def system_workspaces(request: Request) -> list[dict[str, object]]:
            return access.list_workspaces(user(request))

        @router.patch("/workspaces/{workspace_id}")
        def update_workspace(
            workspace_id: UUID,
            payload: WorkspaceAdministrationInput,
            request: Request,
        ) -> dict[str, object]:
            return access.update_workspace(
                user(request),
                workspace_id,
                name=payload.name,
                operational_status=payload.operational_status,
                ai_execution_enabled=payload.ai_execution_enabled,
            )

        @router.get("/roles")
        def system_roles(request: Request) -> list[dict[str, object]]:
            return access.list_system_roles(user(request))

        @router.get("/users")
        def system_users(request: Request) -> list[dict[str, object]]:
            return access.list_users(user(request))

        @router.get("/access")
        def system_access(request: Request) -> list[dict[str, object]]:
            return access.list_system_access(user(request))

        @router.post("/access", status_code=204)
        def assign_system_access(
            payload: SystemAccessInput, request: Request
        ) -> None:
            access.assign_system_access(
                user(request), payload.user_id, payload.role_id
            )

        @router.delete("/access/{user_id}/{role_id}", status_code=204)
        def revoke_system_access(
            user_id: UUID, role_id: UUID, request: Request
        ) -> None:
            access.revoke_system_access(user(request), user_id, role_id)

        @router.get("/permissions")
        def system_permission_catalogue(request: Request) -> list[dict[str, object]]:
            access.require_system(user(request), Permission.ROLES_READ)
            return _permission_catalogue()

    @router.get("/me/workspaces")
    def workspaces(request: Request) -> list[dict[str, object]]:
        return access.discover_workspaces(user(request))

    @router.get("/workspaces/{workspace_id}/members")
    def members(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return access.list_members(user(request), workspace_id)

    @router.patch("/workspaces/{workspace_id}/members/{member_id}", status_code=204)
    def change_role(
        workspace_id: UUID, member_id: UUID, payload: RoleAssignment, request: Request
    ) -> None:
        access.change_member_role(user(request), workspace_id, member_id, payload.role_id)

    @router.delete("/workspaces/{workspace_id}/members/{member_id}", status_code=204)
    def remove_member(workspace_id: UUID, member_id: UUID, request: Request) -> None:
        access.remove_member(user(request), workspace_id, member_id)

    @router.get("/workspaces/{workspace_id}/roles")
    def roles(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return access.list_roles(user(request), workspace_id)

    @router.post("/workspaces/{workspace_id}/roles", status_code=201)
    def create_role(workspace_id: UUID, payload: RoleInput, request: Request) -> dict[str, UUID]:
        return {
            "id": access.create_role(user(request), workspace_id, payload.name, payload.permissions)
        }

    @router.patch("/workspaces/{workspace_id}/roles/{role_id}", status_code=204)
    def update_role(
        workspace_id: UUID, role_id: UUID, payload: RoleInput, request: Request
    ) -> None:
        access.update_role(user(request), workspace_id, role_id, payload.name, payload.permissions)

    @router.delete("/workspaces/{workspace_id}/roles/{role_id}", status_code=204)
    def delete_role(workspace_id: UUID, role_id: UUID, request: Request) -> None:
        try:
            access.delete_role(user(request), workspace_id, role_id)
        except AccessConflict:
            raise HTTPException(409, "role is in use") from None

    @router.get("/workspaces/{workspace_id}/permissions")
    def permissions(workspace_id: UUID) -> list[str] | list[dict[str, object]]:
        del workspace_id
        if system:
            return _permission_catalogue()
        return [value.value for value in Permission]

    @router.get("/workspaces/{workspace_id}/teams")
    def teams(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return access.list_teams(user(request), workspace_id)

    @router.post("/workspaces/{workspace_id}/teams", status_code=201)
    def create_team(workspace_id: UUID, payload: NamedInput, request: Request) -> dict[str, UUID]:
        return {
            "id": access.save_team(user(request), workspace_id, payload.name, payload.description)
        }

    @router.patch("/workspaces/{workspace_id}/teams/{team_id}", status_code=204)
    def update_team(
        workspace_id: UUID, team_id: UUID, payload: NamedInput, request: Request
    ) -> None:
        access.save_team(user(request), workspace_id, payload.name, payload.description, team_id)

    @router.delete("/workspaces/{workspace_id}/teams/{team_id}", status_code=204)
    def delete_team(workspace_id: UUID, team_id: UUID, request: Request) -> None:
        access.delete_team(user(request), workspace_id, team_id)

    @router.put("/workspaces/{workspace_id}/teams/{team_id}/members/{member_id}", status_code=204)
    def add_team_member(
        workspace_id: UUID, team_id: UUID, member_id: UUID, request: Request
    ) -> None:
        access.set_team_member(user(request), workspace_id, team_id, member_id, True)

    @router.delete(
        "/workspaces/{workspace_id}/teams/{team_id}/members/{member_id}", status_code=204
    )
    def delete_team_member(
        workspace_id: UUID, team_id: UUID, member_id: UUID, request: Request
    ) -> None:
        access.set_team_member(user(request), workspace_id, team_id, member_id, False)

    @router.get("/workspaces/{workspace_id}/invitations")
    def invitations(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return access.list_invitations(user(request), workspace_id)

    @router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}", status_code=204)
    def revoke(workspace_id: UUID, invitation_id: UUID, request: Request) -> None:
        try:
            access.revoke_invitation(user(request), workspace_id, invitation_id)
        except (AccessConflict, AccessNotFound):
            raise HTTPException(409, "invitation cannot be revoked") from None

    return router
