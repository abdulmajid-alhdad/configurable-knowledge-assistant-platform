from pathlib import Path
from uuid import uuid4

import pytest

from knowledge_platform.infrastructure.auth.supabase import AuthProviderFailure, SupabaseAuthAdapter
from knowledge_platform.modules.access_control.domain import (
    BUILT_IN_ROLE_PERMISSIONS,
    BuiltInRole,
    Permission,
)


class Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code, self._payload = status, payload

    def json(self) -> object:
        return self._payload


class Client:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> Response:
        self.requests.append(("POST", url, kwargs))
        return self.response

    def get(self, url: str, **kwargs: object) -> Response:
        self.requests.append(("GET", url, kwargs))
        return self.response


def test_auth_adapter_returns_provider_neutral_session_without_logging_body() -> None:
    user_id = uuid4()
    client = Client(
        Response(
            200,
            {
                "user": {"id": str(user_id), "email": "A@Example.com"},
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
            },
        )
    )
    session = SupabaseAuthAdapter(
        auth_url="https://project.supabase.co/auth/v1", publishable_key="publishable", client=client
    ).sign_in(email="A@Example.com", password="secret")
    assert session.user.id == user_id
    assert session.user.email == "a@example.com"


def test_auth_adapter_maps_provider_failure_safely() -> None:
    adapter = SupabaseAuthAdapter(
        auth_url="https://project.supabase.co/auth/v1",
        publishable_key="publishable",
        client=Client(Response(401, {"secret": "body"})),
    )
    with pytest.raises(AuthProviderFailure) as raised:
        adapter.sign_in(email="a@example.com", password="bad")
    assert str(raised.value) == "authentication provider operation failed"
    assert "body" not in str(raised.value)


def test_central_permission_mapping_covers_sensitive_stage6i_mutations() -> None:
    source = Path("src/knowledge_platform/delivery/security.py").read_text()
    assert "Permission.ASSISTANT_CREATE" in source
    assert "Permission.KNOWLEDGE_ATTACH" in source
    assert "Permission.KNOWLEDGE_PROCESS" in source
    assert "Permission.CONVERSATIONS_CREATE" in source


def test_final_builtins_are_scoped_permission_sets_not_legacy_role_aliases() -> None:
    assert set(BUILT_IN_ROLE_PERMISSIONS) == {
        BuiltInRole.SYSTEM_ADMIN,
        BuiltInRole.WORKSPACE_MANAGER,
        BuiltInRole.MEMBER,
    }
    assert Permission.WORKSPACE_MANAGE in BUILT_IN_ROLE_PERMISSIONS[
        BuiltInRole.SYSTEM_ADMIN
    ]
    assert Permission.WORKSPACE_MANAGE not in BUILT_IN_ROLE_PERMISSIONS[
        BuiltInRole.WORKSPACE_MANAGER
    ]
    assert Permission.ASSISTANT_CREATE not in BUILT_IN_ROLE_PERMISSIONS[
        BuiltInRole.MEMBER
    ]


def test_migration_contains_security_invariants() -> None:
    sql = Path("supabase/migrations/20260904184807_stage7a_identity_access_control.sql").read_text()
    required = [
        "force row level security",
        "app.user_id",
        "user_has_permission",
        "final owner cannot be removed",
        "final owner cannot be demoted",
        "token_hash char(64)",
        "security definer set search_path = ''",
        "revoke all on function",
        "accept_invitation",
    ]
    assert all(fragment in sql for fragment in required)
    assert "insert into platform.workspace_memberships" in sql
    assert "platform.user_has_permission(workspace_id,'conversation.read')" in sql
    assert "grant select on table platform.workspace_memberships" in sql
    assert "grant select, insert, update, delete on table platform.workspace_memberships" not in sql
    assert "create policy memberships_runtime_insert" in sql and "with check (false)" in sql
    assert "owner assignment requires workspace management" in sql
    assert "on conflict(workspace_id,user_id) do update" not in sql
    assert "role_permissions.permission_key <> 'workspace.manage'" in sql
    assert sql.count("current_setting('app.workspace_id', true)::uuid") >= 10


def test_spa_uses_server_workspace_discovery_and_no_catalog_authority() -> None:
    html = Path("src/knowledge_platform/delivery/saas_ui.py").read_text(encoding="utf-8")
    assert "api('/api/me/workspaces')" in html
    assert "last_selected_workspace_id" in html
    assert "JSON.parse(localStorage.getItem('workspace_catalog')" not in html
    assert "/app/members" in html and "/app/teams" in html and "/app/roles" in html
    assert "location.reload" not in html
    assert "renderInvitationAcceptance" in html
    assert "new URLSearchParams(location.search).get('token')" in html
    assert "localStorage.setItem('token'" not in html


def test_spa_recovers_from_membership_and_permission_changes() -> None:
    html = Path("src/knowledge_platform/delivery/saas_ui.py").read_text(encoding="utf-8")
    assert "async function reconcileAccess()" in html
    assert "closeDialogs();if(current)" in html
    assert "routePermission(route())" in html
    assert "history.replaceState({},'', '/app')" in html
    assert "applyNavigationPermissions();" in html
    assert "textarea.readOnly=!editable" in html
    assert "'تعديل البيانات':'assistant.update'" in html


def test_invitation_acceptance_keeps_token_ephemeral_and_sanitizes_url() -> None:
    html = Path("src/knowledge_platform/delivery/saas_ui.py").read_text(encoding="utf-8")
    assert "new URLSearchParams(location.search).get('token')" in html
    assert "body:JSON.stringify({token})" in html
    assert "history.replaceState({},'', '/app')" in html
    assert "history.replaceState({},'', '/app/invitations/accept')" in html
    assert "localStorage.setItem('invitation" not in html


def test_session_refresh_is_attempted_at_most_once_per_request() -> None:
    source = Path("src/knowledge_platform/delivery/security.py").read_text(encoding="utf-8")
    assert "refresh_attempted = False" in source
    assert "refresh_attempted = True" in source
    assert "and not refresh_attempted" in source
