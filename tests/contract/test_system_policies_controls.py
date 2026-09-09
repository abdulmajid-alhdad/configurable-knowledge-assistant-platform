"""Focused contracts for the corrected System policy-control surface."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def load_workspace_admin_mutation(source: str):  # type: ignore[no-untyped-def]
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_workspace_admin_mutation"
    )
    namespace = {"re": re, "UNSAFE": {"POST", "PATCH", "PUT", "DELETE"}}
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, "security.py", "exec"), namespace)
    return namespace["_workspace_admin_mutation"]


def test_policy_loads_and_save_feedback_are_independent() -> None:
    pages = read("frontend/system/controls-pages.js")
    section = pages.split("export function policiesPage", 1)[1].split(
        "function money", 1
    )[0]

    assert "Promise.allSettled" in section
    assert "governanceError" in section
    assert "securityError" in section
    assert "تعذر تحميل السياسات التشغيلية." in section
    assert "تعذر تحميل ضوابط الأمان." in section
    assert "تعذر حفظ التغييرات." in section
    assert "تم حفظ التغييرات." in section
    assert "policyContent.append(apiError(error))" not in section
    assert "securityContent.append(apiError(error))" not in section
    assert "workspaceCache.set(cacheKey(resource), data)" in section
    assert "invalidate(resource)" not in section
    assert 'notify("تم حفظ التغييرات.");\n              render();' not in section


def test_policy_surface_retains_only_accepted_controls() -> None:
    pages = read("frontend/system/controls-pages.js")
    section = pages.split("export function policiesPage", 1)[1].split(
        "function money", 1
    )[0]

    for key in (
        "knowledge_processing_enabled",
        "knowledge_source_addition_enabled",
        "invitations_enabled",
        "max_invitation_expiry_days",
        "api_keys_enabled",
    ):
        assert key in pages
    assert "assistant_creation_enabled" not in pages
    assert (
        'getJSON(`/api/system/workspaces/${selectedWorkspace}/governance`)'
        in section
    )
    assert (
        'getJSON(`/api/system/workspaces/${selectedWorkspace}/security`)' in section
    )


def test_system_governance_update_audits_without_workspace_member_notification() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/administration.py"
    )
    section = persistence.split("def update_governance", 1)[1].split(
        "def audit", 1
    )[0]

    assert "Permission.GOVERNANCE_MANAGE" in section
    assert "require_governance" not in section
    assert '"governance.updated"' in section
    assert "enqueue_notification" not in section


def test_invitation_and_api_key_controls_have_enforced_backend_paths() -> None:
    identity_sql = read(
        "supabase/migrations/20260908202313_identity_provisioning_activation.sql"
    )
    stage1_sql = read(
        "supabase/migrations/20260906070000_stage1_authority_data_foundation.sql"
    )

    assert (
        "platform.check_invitation_creation(target_workspace, target_expiry)"
        in identity_sql
    )
    invitation_check = stage1_sql.split(
        "create or replace function platform.check_invitation_creation", 1
    )[1].split("create or replace function", 1)[0]
    assert "settings.invitations_enabled" in invitation_check
    assert "settings.max_invitation_expiry_days" in invitation_check
    api_key_check = stage1_sql.split(
        "create or replace function platform.check_api_key_creation", 1
    )[1].split("create or replace function", 1)[0]
    assert "api_keys_enabled" in api_key_check


def test_workspace_knowledge_operations_reach_workspace_policy_guards() -> None:
    security = read("src/knowledge_platform/delivery/security.py")
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")

    mutation_filter = security.split("def _workspace_admin_mutation", 1)[1].split(
        "def _workspace_system_surface", 1
    )[0]
    assert 'method == "POST"' in mutation_filter
    assert 'r"/api/workspaces/[^/]+/sources"' in mutation_filter
    assert "(?:upload|process)" in mutation_filter
    assert '"/sources"' in mutation_filter

    workspace_admin_mutation = load_workspace_admin_mutation(security)

    workspace = "00000000-0000-0000-0000-000000000001"
    source = "00000000-0000-0000-0000-000000000002"
    assistant = "00000000-0000-0000-0000-000000000003"
    assert not workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources", "POST"
    )
    assert not workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources/{source}/upload", "POST"
    )
    assert not workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources/{source}/process", "POST"
    )
    assert workspace_admin_mutation(
        f"/api/workspaces/{workspace}/assistants/{assistant}/sources/{source}",
        "POST",
    )
    assert workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources/{source}", "DELETE"
    )

    create_route = delivery.split("def create_source", 2)[2].split(
        '@router.get("/workspaces/{workspace_id}/sources"', 1
    )[0]
    process_route = delivery.split("def process_source", 1)[1].split(
        "return router", 1
    )[0]
    assert "administration is not None and not system" in create_route
    assert "knowledge_source_addition_enabled" in create_route
    assert "administration is not None and not system" in process_route
    assert "knowledge_processing_enabled" in process_route

    create_service = bootstrap.split("def create_source", 1)[1].split(
        "def list_sources", 1
    )[0]
    process_service = bootstrap.split("def process_source", 1)[1].split(
        "def attach_source", 1
    )[0]
    assert "if system_operation:" in create_service
    assert "Permission.SYSTEM_KNOWLEDGE_CREATE" in create_service
    assert "knowledge_source_addition_enabled" in create_service
    assert "if system_operation:" in process_service
    assert "Permission.SYSTEM_KNOWLEDGE_PROCESS" in process_service
    assert "knowledge_processing_enabled" in process_service
    assert process_service.index("knowledge_processing_enabled") < process_service.index(
        "require_ai_execution"
    )
    assert process_service.index("require_ai_execution") < process_service.index(
        "source_processing_service"
    )


def test_policy_guards_are_workspace_specific_and_immediately_resolved() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/administration.py"
    )
    lookup = persistence.split("def governance_enabled", 1)[1].split(
        "def require_governance", 1
    )[0]
    update = persistence.split("def update_governance", 1)[1].split(
        "def audit", 1
    )[0]

    assert (
        "where workspace_id=:workspace and setting_key=:key and is_active" in lookup
    )
    assert '"workspace": workspace_id' in lookup
    assert (
        "where workspace_id=:workspace and setting_key=:key and is_active" in update
    )
    assert "governance_cache" not in persistence
    assert "operational_status" not in update
    assert "ai_execution_enabled" not in update
