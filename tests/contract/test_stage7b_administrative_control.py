from pathlib import Path

from knowledge_platform.modules.access_control.domain import (
    MEMBER_PERMISSIONS,
    SYSTEM_ADMIN_PERMISSIONS,
    Permission,
)


ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "supabase/migrations/20260904225858_stage7b_administrative_control.sql"
UI = ROOT / "src/knowledge_platform/delivery/saas_ui.py"
SECURITY = ROOT / "src/knowledge_platform/delivery/security.py"
API = ROOT / "src/knowledge_platform/delivery/administration_api.py"
SERVICE = ROOT / "src/knowledge_platform/infrastructure/persistence/administration.py"


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
    stage1 = text(
        ROOT / "supabase/migrations/20260906070000_stage1_authority_data_foundation.sql"
    )
    delivery = (ROOT / "src/knowledge_platform/delivery/product_api.py").read_text(
        encoding="utf-8"
    )
    assert "assistant_creation_enabled" in migration
    assert "set is_active=false where setting_key='assistant_creation_enabled'" in stage1
    assert "assistant_creation_enabled" not in delivery
    assert "knowledge_source_addition_enabled" in delivery
    assert "knowledge_processing_enabled" in migration
    assert "knowledge_processing_enabled" in delivery
    assert "require_governance" in delivery


def test_stage7b_api_is_paginated_and_permission_mapped() -> None:
    api, security = text(API), text(SECURITY)
    assert 'Query(50, ge=1, le=100)' in api
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
    forbidden = ("password", "access_token", "refresh_token", "embedding", "raw_prompt")
    assert all(item not in service for item in forbidden)
    assert "metadata or {}" in service


def test_spa_has_deep_routes_and_local_renderers() -> None:
    ui = text(UI)
    for route in (
        "/app/usage",
        "/app/governance",
        "/app/audit",
        "/app/notifications",
        "/app/admin-operations",
    ):
        assert f'data-route="{route}"' in ui
        assert f"p==='{route}'" in ui
    assert "history.pushState" in ui
    assert "popstate" in ui
    assert "location.reload" not in ui
    assert "renderNotificationsStage7b" in ui
    assert "notifications/'+item.id+'/read" in ui
    assert "a[data-route]" in ui
    assert "stage7bCache" in ui
    assert "stage7bInflight" in ui
    assert "stage7bPrefetch" in ui
    assert "stage7bMetrics.coalesced" in ui
    assert "stage7bMetrics.cacheHits" in ui
    assert "stage7bMetrics.swrRefreshes" in ui
    assert "stage7bMetrics.prefetches" in ui


def test_notification_optimistic_contract_and_rollback() -> None:
    ui = text(UI)
    assert "data.unread_count=0" in ui
    assert "data.unread_count=Math.max(0" in ui
    assert "const snapshot={unread_count:data.unread_count" in ui
    assert "toast('تعذر تحديث حالة الإشعارات.')" in ui
    assert "toast('تعذر تعليم الإشعار كمقروء.')" in ui


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
    ui = text(UI)
    for key in ("members", "invitations", "teams", "roles", "permissions"):
        assert f"stage7aAccessKey('{key}')" in ui
    assert "renderAccessPage=renderAccessPageCached" in ui
    assert "const stage7bPrefetchWithAccess=stage7bPrefetch" in ui
    assert "members.read" in ui and "teams.read" in ui and "roles.read" in ui
    assert "invitations.read" in ui


def test_stage7a_admin_cache_invalidation_and_stale_guard() -> None:
    ui = text(UI)
    assert "stage7bRequest(key" in ui
    assert "stage7bVisible(generation,workspace)" in ui
    assert "stage7bCache.delete(stage7aAccessKey('members'))" in ui
    assert "stage7bCache.delete(stage7aAccessKey('teams'))" in ui
    assert "stage7bCache.delete(stage7aAccessKey('roles'))" in ui
    assert "stage7bCache.delete(stage7aAccessKey('invitations'))" in ui
    assert "stage7bCache.clear();stage7bInflight.clear();stage7bClearClientState" in ui


def test_stage7a_routes_keep_route_host_during_cached_navigation() -> None:
    ui = text(UI)
    assert "if(cached){stage7aRenderAccess" in ui
    assert "else root.replaceChildren(pageToolbar('إدارة الوصول إلى مساحة العمل.'),localLoading" in ui
    assert "window.location" not in ui


def test_administrative_dom_render_contract_and_arabic_permissions() -> None:
    ui = text(UI)
    assert "HTMLTableCellElement" in ui
    assert "el('td','',buttons)" not in ui
    assert "stage7aPermissionLabels" in ui
    permissions = (
        "workspace.read workspace.manage assistant.read assistant.create assistant.update "
        "knowledge.read knowledge.create knowledge.process knowledge.attach conversation.read "
        "conversation.ask evaluation.read operations.read settings.read members.read members.manage "
        "teams.read teams.manage roles.read roles.manage invitations.read invitations.manage usage.read "
        "governance.read governance.manage audit.read notifications.read notifications.manage"
    ).split()
    assert len(permissions) == 28
    assert all(f"'{code}':" in ui for code in permissions)
    assert "صلاحية غير معروفة" in ui
    assert "دور أساسي — غير قابل للتعديل" in ui


def test_admin_actions_are_nodes_and_cache_is_data_only() -> None:
    ui = text(UI)
    assert "actionCell=el('td')" in ui
    assert "cell.append(value)" in ui
    assert "stage7aRenderAccess" in ui
    assert "stage7bCache.set(key,items)" in ui
    assert "stage7bCache.set(key,root" not in ui
    assert "[object HTMLDivElement]" not in ui
    assert "[object HTMLElement]" not in ui
    assert "[object Object]" not in ui


def test_admin_cell_contract_supports_nested_node_arrays_and_invitation_states() -> None:
    ui = text(UI)
    assert "function appendCellContent(cell,value)" in ui
    assert "if(Array.isArray(value))" in ui
    assert "value.forEach(item=>appendCellContent(cell,item))" in ui
    assert "stage7aRoleLabels" in ui
    assert "OWNER:'المالك'" in ui
    assert "ADMIN:'المدير'" in ui
    assert "MEMBER:'العضو'" in ui
    assert "VIEWER:'المشاهد'" in ui
    for status, label in (("pending", "معلقة"), ("accepted", "مقبولة"), ("revoked", "ملغاة"), ("expired", "منتهية")):
        assert f"{status}:'{label}'" in ui
    assert "inv.status==='pending'&&allowed('invitations.manage')" in ui
    assert "stage7aInvitationDisplay" in ui


def test_roles_permission_producer_passes_nodes_not_stringified_arrays() -> None:
    ui = text(UI)
    assert "const stage7aAccessRowsBase=stage7aAccessRows" in ui
    assert "permissionCell.append(...permissions)" in ui
    assert "permissionCell.append(...permissions)" in ui
    assert "permissionNodes.join" not in ui
    assert "String(permission" not in ui
