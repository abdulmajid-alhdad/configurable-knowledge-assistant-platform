"""Focused contracts for the least-privilege Assistant update path."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / (
    "supabase/migrations/20260908192635_assistant_protected_update_path.sql"
)
REPOSITORIES = ROOT / "src/knowledge_platform/infrastructure/persistence/repositories.py"
BOOTSTRAP = ROOT / "src/knowledge_platform/bootstrap/application.py"
PRODUCT_API = ROOT / "src/knowledge_platform/delivery/product_api.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(sql: str) -> str:
    return sql.split("as $assistant_protected_update$", 1)[1].split(
        "$assistant_protected_update$;", 1
    )[0]


def test_protected_function_is_system_authorized_and_hardened() -> None:
    sql = read(MIGRATION).lower()

    assert "security definer" in sql
    assert "set search_path = ''" in sql
    assert "user_has_system_permission('assistant.update')" in sql
    assert "assistant_update_system_permission_required" in sql
    assert "revoke all on function platform.update_assistant_administration" in sql
    assert "from public" in sql
    assert "from anon, authenticated" in sql
    assert "grant execute on function platform.update_assistant_administration" in sql
    assert "to knowledge_platform_runtime" in sql


def test_update_is_same_workspace_only_and_preserves_identity_and_ownership() -> None:
    body = function_body(read(MIGRATION).lower())
    update = body.split("update platform.assistants", 1)[1].split(
        "get diagnostics", 1
    )[0]

    assert "where id = target_assistant" in update
    assert "and workspace_id = target_workspace" in update
    assert "assistant_not_found_in_workspace" in body
    assert "set workspace_id" not in update
    assert "set id" not in update
    assert "retrieval_configuration" not in update


def test_function_exposes_only_the_accepted_mutable_fields() -> None:
    sql = read(MIGRATION).lower()
    signature = sql.split("create function platform.update_assistant_administration", 1)[
        1
    ].split(") returns boolean", 1)[0]
    body = function_body(sql)

    for field in (
        "requested_name",
        "requested_description",
        "requested_instructions",
        "requested_language",
        "requested_provider",
        "requested_model_reference",
    ):
        assert field in signature
    assert "requested_workspace" not in signature
    assert "requested_retrieval" not in signature
    assert "model_configuration" in body
    assert "jsonb_build_object" in body


def test_runtime_has_no_direct_assistant_update_privilege() -> None:
    sql = read(MIGRATION).lower()

    assert "revoke update on table platform.assistants from knowledge_platform_runtime" in sql
    assert "grant update on" not in sql
    assert "grant all" not in sql
    assert "bypassrls" not in sql


def test_repository_uses_only_the_protected_update_function() -> None:
    repositories = read(REPOSITORIES)
    section = repositories.split("def save_reconfiguration", 1)[1].split(
        "class AssistantKnowledgeSourceRepository", 1
    )[0]

    assert "platform.update_assistant_administration" in section
    assert "update(AssistantRecord)" not in section
    assert '"workspace": workspace_id.value' in section
    assert '"assistant": previous.id.value' in section
    assert "retrieval_configuration" not in section


def test_database_operation_owns_one_safe_audit_event() -> None:
    sql = read(MIGRATION).lower()
    bootstrap = read(BOOTSTRAP)
    update_service = bootstrap.split("def update_assistant", 1)[1].split(
        "def create_source", 1
    )[0]

    assert "platform.append_audit_event" in function_body(sql)
    assert "'assistant.updated'" in function_body(sql)
    assert "self.audit(" not in update_service


def test_delivery_rejects_unknown_fields_and_requires_system_permission() -> None:
    delivery = read(PRODUCT_API)
    payload = delivery.split("class AssistantInput", 1)[1].split(
        "class SourceCreate", 1
    )[0]
    route = delivery.split(
        '@router.patch("/workspaces/{workspace_id}/assistants/{assistant_id}"', 1
    )[1].split('@router.post("/workspaces/{workspace_id}/sources"', 1)[0]

    assert 'ConfigDict(extra="forbid")' in payload
    assert "Permission.ASSISTANT_UPDATE" in route
