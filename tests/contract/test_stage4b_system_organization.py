"""Focused static contracts for Stage 4B System organization surfaces."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_system_route_registry_keeps_fourteen_routes_and_functionalizes_only_stage4b() -> None:
    routes = read("frontend/system/routes.js")
    assert routes.count('system("/system') == 14
    for page in (
        "SYSTEM_PAGES.home",
        "SYSTEM_PAGES.workspaces",
        "SYSTEM_PAGES.assistants",
        "SYSTEM_PAGES.knowledge",
        "SYSTEM_PAGES.members",
        "SYSTEM_PAGES.teams",
        "SYSTEM_PAGES.roles",
    ):
        assert page in routes
    for deferred in (
        'system("/system/policies"',
        'system("/system/usage"',
        'system("/system/providers"',
        'system("/system/credentials"',
        'system("/system/conversations"',
        'system("/system/audit"',
        'system("/system/access"',
    ):
        assert deferred in routes


def test_system_pages_use_only_same_origin_platform_api_boundaries() -> None:
    pages = read("frontend/system/pages.js")
    assert 'from "/assets/shared/api.js"' in pages
    assert "/api/system/workspaces" in pages
    assert "/api/system/roles" in pages
    assert "/api/system/permissions" in pages
    assert "supabase" not in pages.lower()
    assert "openrouter" not in pages.lower()
    assert "innerHTML" not in pages


def test_stage4b_surfaces_have_real_operations_without_forbidden_product_actions() -> None:
    pages = read("frontend/system/pages.js")
    required = (
        "workspaceForm",
        "assistantForm",
        "bindingManager",
        "createSourceForm",
        "sourceBindings",
        "invitationForm",
        "memberRoleForm",
        "teamForm",
        "teamMembers",
        "customRoleForm",
        "permissionSelection",
    )
    assert all(symbol in pages for symbol in required)
    assert "assistant_creation_enabled" not in pages
    assert "حذف المساعد" not in pages
    assert "حذف المصدر" not in pages
    assert "إزالة المصدر" not in pages


def test_system_permissions_are_loaded_before_authority_filtered_shell() -> None:
    entry = read("frontend/system/entry.js")
    assert 'getJSON("/api/system/me/permissions")' in entry
    assert "window.__controlPlanePermissions" in entry
    assert entry.index("window.__controlPlanePermissions =") < entry.index(
        'return startSurface("system", SYSTEM_ROUTES)'
    )


def test_delivery_exposes_system_workspace_and_catalogue_read_contracts() -> None:
    delivery = read("src/knowledge_platform/delivery/access_control_api.py")
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    security = read("src/knowledge_platform/delivery/security.py")
    assert '@router.get("/workspaces")' in delivery
    assert '@router.patch("/workspaces/{workspace_id}")' in delivery
    assert '@router.get("/roles")' in delivery
    assert '@router.get("/permissions")' in delivery
    assert "PERMISSION_CATALOG" in delivery
    assert "def list_workspaces" in persistence
    assert "def update_workspace" in persistence
    assert "Permission.SYSTEM_WORKSPACES_READ" in persistence
    assert "Permission.WORKSPACE_MANAGE" in persistence
    assert "Permission.GOVERNANCE_MANAGE" in persistence
    assert "system_path in {\"/api/roles\", \"/api/permissions\"}" in security
    assert "'WORKSPACE'::text as canonical_scope" in persistence
    assert "r.canonical_scope" not in persistence


def test_system_organization_routes_are_registered_with_canonical_methods() -> None:
    delivery = read("src/knowledge_platform/delivery/access_control_api.py")
    expected = (
        '@router.get("/me/permissions")',
        '@router.get("/workspaces")',
        '@router.patch("/workspaces/{workspace_id}")',
        '@router.get("/roles")',
        '@router.get("/permissions")',
        '@router.get("/workspaces/{workspace_id}/members")',
        '@router.post("/workspaces/{workspace_id}/invitations"',
        '@router.post("/workspaces/{workspace_id}/teams"',
        '@router.post("/workspaces/{workspace_id}/roles"',
    )
    assert all(route in delivery for route in expected)


def test_workspace_state_update_preserves_suspension_ai_invariant() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    assert (
        'effective_ai = ai_execution_enabled and operational_status != "SUSPENDED"'
        in persistence
    )
    assert "platform.update_workspace_operational_state" in persistence


def test_workspace_catalogue_uses_only_columns_present_in_workspace_schema() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    catalogue_query = persistence.split("def list_workspaces", 1)[1].split(
        "def permissions", 1
    )[0]
    assert "select id,name,operational_status,ai_execution_enabled" in catalogue_query
    assert "workspace_settings" in catalogue_query
    assert "display_name" in catalogue_query
    assert "set_config('app.workspace_id'" in catalogue_query
    assert "created_at" not in catalogue_query


def test_custom_role_ui_is_workspace_scoped_and_built_ins_are_immutable() -> None:
    pages = read("frontend/system/pages.js")
    assert 'item.scope === "WORKSPACE" && item.active && item.delegable' in pages
    assert 'role.role_kind === "built_in"' in pages
    assert 'scope === "WORKSPACE" && !builtIn && !deprecated' in pages
    assert "customRoleForm(workspaceId" in pages


def test_system_knowledge_binding_uses_same_workspace_paths() -> None:
    pages = read("frontend/system/pages.js")
    assert "source.workspace_id}/assistants" in pages
    assert "source.workspace_id}/assistants/${assistant.id}/sources/${source.id}" in pages
    assert "item.workspace_id}/assistants/${item.id}/sources/${source.id}" in pages
    assert "عابر لمساحات العمل" in pages


def test_stage4c_surfaces_are_not_implemented_by_stage4b_module() -> None:
    pages = read("frontend/system/pages.js")
    for exported in (
        "policiesPage",
        "usagePage",
        "providersPage",
        "credentialsPage",
        "systemConversationsPage",
        "auditPage",
        "systemAccessPage",
    ):
        assert exported not in pages
