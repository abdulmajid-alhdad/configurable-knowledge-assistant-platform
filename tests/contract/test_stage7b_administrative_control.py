from pathlib import Path

from knowledge_platform.modules.access_control.domain import (
    MEMBER_PERMISSIONS,
    SYSTEM_ADMIN_PERMISSIONS,
    Permission,
)

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "supabase/migrations/20260904225858_stage7b_administrative_control.sql"
SECURITY = ROOT / "src/knowledge_platform/delivery/security.py"
API = ROOT / "src/knowledge_platform/delivery/administration_api.py"
SERVICE = ROOT / "src/knowledge_platform/infrastructure/persistence/administration.py"
SYSTEM_PAGES = ROOT / "frontend/system/pages.js"
CONTROL_PAGES = ROOT / "frontend/system/controls-pages.js"
ROUTES = ROOT / "frontend/system/routes.js"
DOM = ROOT / "frontend/shared/dom.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_stage7b_permission_boundaries_are_deliberate() -> None:
    assert Permission.USAGE_READ in SYSTEM_ADMIN_PERMISSIONS
    assert Permission.GOVERNANCE_MANAGE in SYSTEM_ADMIN_PERMISSIONS
    assert Permission.AUDIT_READ in SYSTEM_ADMIN_PERMISSIONS
    assert Permission.NOTIFICATIONS_READ in MEMBER_PERMISSIONS
    assert Permission.GOVERNANCE_MANAGE not in MEMBER_PERMISSIONS
    assert Permission.AUDIT_READ not in MEMBER_PERMISSIONS


def test_migration_creates_workspace_isolated_administrative_models() -> None:
    sql = text(MIGRATION)
    for table in (
        "usage_events",
        "governance_settings",
        "audit_events",
        "notifications",
        "administrative_operations",
    ):
        assert f"create table platform.{table}" in sql
        assert f"alter table platform.{table} enable row level security" in sql
        assert f"alter table platform.{table} force row level security" in sql
    assert "references platform.workspace_memberships" in sql
    assert "from anon, authenticated" in sql


def test_append_paths_are_security_definer_and_not_public() -> None:
    sql = text(MIGRATION)
    for function in (
        "append_audit_event",
        "record_usage_event",
        "record_administrative_operation",
        "enqueue_notification",
    ):
        assert f"create function platform.{function}" in sql
        assert f"revoke all on function platform.{function}" in sql
    assert "security definer set search_path = ''" in sql
    assert "grant insert on platform.audit_events" not in sql
    assert "grant insert on platform.usage_events" not in sql


def test_governance_is_persisted_and_enforced_by_product_delivery() -> None:
    migration = text(MIGRATION)
    stage1 = text(ROOT / "supabase/migrations/20260906070000_stage1_authority_data_foundation.sql")
    delivery = text(ROOT / "src/knowledge_platform/delivery/product_api.py")
    assert "assistant_creation_enabled" in migration
    assert "set is_active=false where setting_key='assistant_creation_enabled'" in stage1
    assert "assistant_creation_enabled" not in delivery
    assert "knowledge_source_addition_enabled" in delivery
    assert "knowledge_processing_enabled" in migration
    assert "knowledge_processing_enabled" in delivery
    assert "require_governance" in delivery


def test_stage7b_api_is_paginated_and_permission_mapped() -> None:
    api, security = text(API), text(SECURITY)
    assert "Query(50, ge=1, le=100)" in api
    for route, permission in (
        ("/usage", "USAGE_READ"),
        ("/governance", "GOVERNANCE_READ"),
        ("/audit", "AUDIT_READ"),
        ("/notifications", "NOTIFICATIONS_READ"),
        ("/administrative-operations", "OPERATIONS_READ"),
    ):
        assert route in api
        assert permission in security


def test_audit_metadata_does_not_accept_sensitive_product_payloads() -> None:
    service = text(SERVICE)
    assert "_SENSITIVE_METADATA_TERMS" in service
    assert all(item in service for item in ("password", "secret", "token", "api_key"))
    assert "_safe_audit_metadata" in service
    assert "metadata or {}" in service


def test_spa_has_deep_routes_and_local_renderers() -> None:
    pages, controls, routes = text(SYSTEM_PAGES), text(CONTROL_PAGES), text(ROUTES)
    for route in (
        "/system/policies",
        "/system/usage",
        "/system/providers",
        "/system/credentials",
        "/system/conversations",
        "/system/audit",
        "/system/access",
    ):
        assert route in routes
    assert "export function policiesPage" in controls
    assert "export function usagePage" in controls
    assert "export function systemConversationsPage" in controls
    assert "history.pushState" not in controls
    assert "innerHTML" not in pages + controls


def test_notification_contract_remains_backend_owned_and_scoped() -> None:
    api, service = text(API), text(SERVICE)
    assert '@router.get("/notifications")' in api
    assert '@router.patch("/notifications/read", status_code=204)' in api
    assert '@router.patch("/notifications/{notification_id}/read", status_code=204)' in api
    assert "recipient_user_id" in service
    assert "coalesce(read_at,now())" in service


def test_notifications_are_recipient_scoped_and_have_read_state() -> None:
    sql = text(MIGRATION)
    assert "recipient_user_id = platform.current_user_id()" in sql
    assert "read_at timestamptz" in sql
    assert "notifications_recipient_unread_idx" in sql


def test_history_filters_cast_nullable_parameters() -> None:
    service = text(SERVICE)
    assert "cast(:action as text) is null" in service
    assert "cast(:status as text) is null" in service


def test_stage7a_admin_routes_extend_shared_cache_and_prefetch() -> None:
    pages, controls = text(SYSTEM_PAGES), text(CONTROL_PAGES)
    for key in ("members", "invitations", "teams", "roles", "permissions"):
        assert key in pages
    assert "workspaceCache" in pages and "workspaceCache" in controls
    assert "loadResource" in pages
    assert "staleWhileRevalidate" in pages + controls


def test_stage7a_admin_cache_invalidation_and_stale_guard() -> None:
    pages, controls = text(SYSTEM_PAGES), text(CONTROL_PAGES)
    assert "workspaceCache.invalidate" in pages + controls
    assert "clear() {" in text(ROOT / "frontend/shared/cache.js")
    assert "isCurrent" in pages + controls


def test_stage7a_routes_keep_route_host_during_cached_navigation() -> None:
    pages, controls = text(SYSTEM_PAGES), text(CONTROL_PAGES)
    assert "host.replaceChildren" in pages + controls
    assert "route-panel" in pages + controls
    assert "window.location.replace" not in pages + controls


def test_administrative_dom_render_contract_and_arabic_permissions() -> None:
    pages = text(SYSTEM_PAGES)
    assert 'el("td"' in pages
    assert "function permissionLabel" in pages
    assert "innerHTML" not in pages
    assert "technicalCode" in pages


def test_admin_actions_are_nodes_and_cache_is_data_only() -> None:
    pages, controls = text(SYSTEM_PAGES), text(CONTROL_PAGES)
    assert "function action" in pages + controls
    assert ".append(" in pages + controls
    assert "workspaceCache.set" in controls
    assert "[object HTMLDivElement]" not in pages + controls
    assert "[object Object]" not in pages + controls


def test_admin_cell_contract_supports_nested_node_arrays_and_invitation_states() -> None:
    dom, pages = text(DOM), text(SYSTEM_PAGES)
    assert "export function appendContent(parent, value)" in dom
    assert "if (Array.isArray(value))" in dom
    assert "value.forEach((item) => appendContent(parent, item));" in dom
    assert "value instanceof Node" in dom
    assert "parent.append(value);" in dom
    assert 'throw new TypeError("Unsupported DOM content")' in dom
    assert 'from "/assets/shared/dom.js"' in pages
    assert "function table" in pages
    assert 'el("td", {}, cell)' in pages
    assert "statusBadge(invitation.status)" in pages
    assert 'can("invitations.manage") && invitation.status === "pending"' in pages
    assert 'action("إلغاء الدعوة"' in pages


def test_roles_permission_producer_passes_nodes_not_stringified_arrays() -> None:
    pages = text(SYSTEM_PAGES)
    assert "function permissionSelection" in pages
    assert "permissions.values()" in pages
    assert "permissionNodes.join" not in pages
    assert "String(permission" not in pages
