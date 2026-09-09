"""Focused contracts for Stage 4 operational correction batch 1."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_workspace_create_and_update_use_authoritative_existing_state_contracts() -> None:
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    pages = read("frontend/system/pages.js")

    assert "ai_execution_enabled: bool = True" in delivery
    assert 'ai_execution_enabled: ai.checked' in pages
    assert "platform.update_workspace_operational_state" in persistence
    assert "platform.update_workspace_settings" in persistence
    update_section = persistence.split("def update_workspace", 1)[1].split(
        "def create_role", 1
    )[0]
    assert "update platform.workspaces" not in update_section
    assert "Permission.WORKSPACE_SETTINGS_MANAGE" in update_section
    assert (
        'effective_ai = ai_execution_enabled and operational_status != "SUSPENDED"'
        in update_section
    )


def test_long_drawers_keep_header_and_actions_reachable() -> None:
    css = read("frontend/styles/foundation.css")
    drawer_rule = css.split(".drawer {", 1)[1].split("}", 1)[0]
    content_rule = css.split(".drawer-content {", 1)[1].split("}", 1)[0]

    assert "display: flex" in drawer_rule
    assert "flex-direction: column" in drawer_rule
    assert "max-height: 100dvh" in drawer_rule
    assert "overflow: hidden" in drawer_rule
    assert "min-height: 0" in content_rule
    assert "overflow-y: auto" in content_rule
    assert ".drawer-content .form-actions" in css
    assert "position: sticky" in css


def test_knowledge_corrections_preserve_artifact_and_reprocess_contracts() -> None:
    pages = read("frontend/system/pages.js")
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    processing = read("src/knowledge_platform/application/knowledge_ingestion.py")

    assert "/sources/${source.id}/artifact" in pages
    assert "artifact.artifact_present" in pages
    assert "لا يمكن استبداله من هذه الواجهة" in pages
    assert 'reprocess = String(source.lifecycle || "").toUpperCase() === "READY"' in pages
    assert 'reprocess ? "إعادة معالجة المصدر" : "معالجة المصدر"' in pages
    assert "reindex=True" in processing
    assert "cast(:reason as text)" in bootstrap
    assert "source processing is disabled" in pages


def test_system_knowledge_operations_bypass_only_workspace_governance() -> None:
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")

    assert "administration is not None and not system" in delivery
    assert "system_operation=True" in delivery
    create_section = bootstrap.split("def create_source", 1)[1].split(
        "def list_sources", 1
    )[0]
    process_section = bootstrap.split("def process_source", 1)[1].split(
        "def attach_source", 1
    )[0]
    for section, system_permission, workspace_permission, policy in (
        (
            create_section,
            "Permission.SYSTEM_KNOWLEDGE_CREATE",
            "Permission.KNOWLEDGE_CREATE",
            "knowledge_source_addition_enabled",
        ),
        (
            process_section,
            "Permission.SYSTEM_KNOWLEDGE_PROCESS",
            "Permission.KNOWLEDGE_PROCESS",
            "knowledge_processing_enabled",
        ),
    ):
        assert "if system_operation:" in section
        assert system_permission in section
        assert workspace_permission in section
        assert policy in section
    assert "require_ai_execution" in process_section


def test_live_operation_fixes_separate_mutation_success_from_refresh() -> None:
    pages = read("frontend/system/pages.js")
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")

    assert "cast(:reason as text)" in bootstrap
    assert "function mutationError" in pages
    assert "function commitWorkspace" in pages
    assert "function commitAssistant" in pages
    assert "function commitSource" in pages
    assert "form.reportValidity()" in pages
    assistant_bindings = pages.split("function bindingManager", 1)[1].split(
        "function assistantDetails", 1
    )[0]
    source_bindings = pages.split("function sourceBindings", 1)[1].split(
        "function sourceDetails", 1
    )[0]
    assert "paint(await assistantBindings(item))" not in assistant_bindings
    assert "paint(await sourceAssistantBindings(source))" not in source_bindings
    assert "updatedIds" in assistant_bindings
    assert "const updated = bindings.map" in source_bindings


def test_workspace_create_contract_accepts_ai_execution_without_direct_table_write() -> None:
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )

    assert "ai_execution_enabled: bool = True" in delivery
    create_section = persistence.split("def create_workspace", 1)[1].split(
        "def update_workspace", 1
    )[0]
    assert "platform.create_workspace_stage1" in create_section
    assert "platform.update_workspace_operational_state" in create_section
    assert "insert into platform.workspaces" not in create_section


def test_teams_are_workspace_bound_and_return_real_members() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    pages = read("frontend/system/pages.js")

    team_save = persistence.split("def save_team", 1)[1].split(
        "def delete_team", 1
    )[0]
    member_mutation = persistence.split("def set_team_member", 1)[1].split(
        "def create_invitation", 1
    )[0]
    assert "workspace_exists" in team_save
    assert "where id=:workspace" in team_save
    assert "team_exists" in member_mutation
    assert "member_exists" in member_mutation
    assert "platform.workspace_memberships" in member_mutation
    assert "t.workspace_id" in persistence
    team_section = pages.split("function teamForm", 1)[1].split(
        "function permissionLabel", 1
    )[0]
    assert '"form-context"' in team_section
    assert "team.member_ids" in team_section
    assert "data.members.find" in team_section


def test_current_identity_and_rbac_schema_cannot_safely_satisfy_deferred_extensions() -> None:
    settings = read("src/knowledge_platform/config/runtime.py")
    auth = read("src/knowledge_platform/infrastructure/auth/supabase.py")
    access = read("src/knowledge_platform/infrastructure/persistence/access_control.py")
    migration = read(
        "supabase/migrations/20260904184807_stage7a_identity_access_control.sql"
    )

    assert "SUPABASE_PUBLISHABLE_KEY" in settings
    assert "service_role" not in settings.lower()
    assert "def create_user" not in auth
    invitations = migration.split("create table platform.invitations", 1)[1].split(
        ");", 1
    )[0]
    assert "team_id" not in invitations
    permissions = access.split("def permissions", 1)[1].split("def require", 1)[0]
    assert "role_permissions" in permissions
    assert "membership_permission" not in permissions
    assert "user_permission" not in permissions
