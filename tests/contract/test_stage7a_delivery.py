"""FastAPI delivery contracts; requires the dependency-complete runtime environment."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from knowledge_platform.delivery.access_control_api import create_access_router
from knowledge_platform.delivery.auth_api import (
    authenticated_destination,
    create_auth_router,
)
from knowledge_platform.delivery.security import ControlPlaneSecurityMiddleware
from knowledge_platform.infrastructure.auth.supabase import AuthSession
from knowledge_platform.modules.access_control.domain import AuthenticatedUser, Permission


@dataclass
class FakeAuth:
    user: AuthenticatedUser

    def sign_in(self, *, email: str, password: str) -> AuthSession:
        del email, password
        return AuthSession(self.user, "access", "refresh", 3600)

    def get_user(self, token: str) -> AuthenticatedUser:
        if token != "access":
            raise RuntimeError("invalid test session")
        return self.user

    def refresh(self, token: str) -> AuthSession:
        assert token == "refresh"
        return AuthSession(self.user, "access", "refresh-2", 3600)

    def sign_out(self, token: str) -> None:
        assert token == "access"


class FakeAccess:
    def __init__(
        self,
        user: AuthenticatedUser,
        workspace: UUID,
        *,
        system_permissions: frozenset[str] = frozenset(),
        has_workspace: bool = True,
        workspace_role: str = "WORKSPACE_MANAGER",
    ) -> None:
        self.user, self.workspace = user, workspace
        self._system_permissions = system_permissions
        self.has_workspace = has_workspace
        self.workspace_role = workspace_role

    def sync_profile(self, user: AuthenticatedUser) -> None:
        assert user == self.user

    def require(self, user: UUID, workspace: UUID, permission: Permission) -> None:
        assert (
            user == self.user.id
            and workspace == self.workspace
            and isinstance(permission, Permission)
        )

    def discover_workspaces(self, user: UUID) -> list[dict[str, object]]:
        assert user == self.user.id
        if not self.has_workspace:
            return []
        return [
            {
                "id": self.workspace,
                "name": "Workspace",
                "role_name": self.workspace_role,
                "permissions": [permission.value for permission in Permission],
            }
        ]

    def system_permissions(self, user: UUID) -> frozenset[str]:
        assert user == self.user.id
        return self._system_permissions

    def list_members(self, user: UUID, workspace: UUID) -> list[dict[str, object]]:
        return [{"user_id": user, "email": self.user.email, "role_name": "OWNER"}]

    def list_roles(self, user: UUID, workspace: UUID) -> list[dict[str, object]]:
        return []

    def list_teams(self, user: UUID, workspace: UUID) -> list[dict[str, object]]:
        return []

    def list_invitations(self, user: UUID, workspace: UUID) -> list[dict[str, object]]:
        return []


def app_client(
    *,
    system_permissions: frozenset[str] = frozenset(),
    has_workspace: bool = True,
    workspace_role: str = "WORKSPACE_MANAGER",
) -> tuple[TestClient, UUID]:
    user = AuthenticatedUser(uuid4(), "owner@example.com")
    workspace = uuid4()
    auth = FakeAuth(user)
    access = FakeAccess(
        user,
        workspace,
        system_permissions=system_permissions,
        has_workspace=has_workspace,
        workspace_role=workspace_role,
    )
    app = FastAPI()
    app.include_router(create_auth_router(auth, access, secure=False))  # type: ignore[arg-type]
    app.include_router(create_access_router(access))  # type: ignore[arg-type]
    app.add_middleware(
        ControlPlaneSecurityMiddleware, auth=auth, access=access, cookie_secure=False
    )
    app.get("/app")(lambda: {"ok": True})
    return TestClient(app, base_url="http://testserver"), workspace


def test_protected_app_and_login_contract() -> None:
    client, _ = app_client()
    assert client.get("/app", follow_redirects=False).status_code == 303
    assert client.get("/login").status_code == 200


def test_sign_in_me_discovery_and_sign_out_cookie_contract() -> None:
    client, workspace = app_client()
    response = client.post(
        "/api/auth/sign-in",
        headers={"origin": "http://testserver"},
        json={"email": "owner@example.com", "password": "secret"},
    )
    assert response.status_code == 200
    assert response.cookies.get("kp_access") == "access"
    assert response.json().get("access_token") is None
    assert response.json()["redirect_to"] == "/app"
    assert client.get("/api/me").status_code == 200
    workspaces = client.get("/api/me/workspaces").json()
    assert workspaces[0]["id"] == str(workspace)
    signed_out = client.post("/api/auth/sign-out", headers={"origin": "http://testserver"})
    assert signed_out.status_code == 204


def test_post_login_destination_prioritizes_canonical_system_authority() -> None:
    user = AuthenticatedUser(uuid4(), "admin@example.com")
    workspace = uuid4()

    system_only = FakeAccess(
        user,
        workspace,
        system_permissions=frozenset({"system_access.read"}),
        has_workspace=False,
    )
    system_and_workspace = FakeAccess(
        user,
        workspace,
        system_permissions=frozenset({"system_access.read"}),
    )
    workspace_manager = FakeAccess(user, workspace, workspace_role="WORKSPACE_MANAGER")
    member = FakeAccess(user, workspace, workspace_role="MEMBER")
    no_authority = FakeAccess(user, workspace, has_workspace=False)

    assert authenticated_destination(system_only, user.id) == "/system"
    assert authenticated_destination(system_and_workspace, user.id) == "/system"
    assert authenticated_destination(workspace_manager, user.id) == "/app"
    assert authenticated_destination(member, user.id) == "/app"
    assert authenticated_destination(no_authority, user.id) == "/app"


def test_sign_in_and_authenticated_login_share_system_first_routing() -> None:
    client, _ = app_client(
        system_permissions=frozenset({"system_access.read"}),
        has_workspace=True,
    )

    response = client.post(
        "/api/auth/sign-in",
        headers={"origin": "http://testserver"},
        json={"email": "owner@example.com", "password": "secret"},
    )
    assert response.status_code == 200
    assert response.json()["redirect_to"] == "/system"

    login = client.get("/login", follow_redirects=False)
    assert login.status_code == 303
    assert login.headers["location"] == "/system"


def test_workspace_permission_middleware_and_access_routes() -> None:
    client, workspace = app_client()
    client.cookies.set("kp_access", "access")
    assert client.get(f"/api/workspaces/{workspace}/members").status_code == 200
    assert client.get(f"/api/workspaces/{workspace}/teams").status_code == 200
    assert client.get(f"/api/workspaces/{workspace}/roles").status_code == 200
    assert client.get(f"/api/workspaces/{workspace}/invitations").status_code == 200
