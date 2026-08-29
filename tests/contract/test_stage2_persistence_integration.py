"""Cross-slice Stage 2 persistence integration contracts."""

from pathlib import Path

from knowledge_platform.infrastructure.persistence.models import (
    AssistantRecord,
    ConversationRecord,
    KnowledgeSourceRecord,
    MessageRecord,
    WorkspaceRecord,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
EXPECTED_MIGRATIONS = [
    "20260829000000_create_private_schemas.sql",
    "20260829010000_runtime_role_workspace_context.sql",
    "20260829020000_workspace_assistant_persistence.sql",
    "20260829030000_knowledge_source_lifecycle_persistence.sql",
    "20260829040000_conversation_messages_persistence.sql",
]


def _migration_sql() -> str:
    return "\n".join(
        (MIGRATIONS / filename).read_text(encoding="utf-8").lower()
        for filename in EXPECTED_MIGRATIONS
    )


def test_migration_chain_is_complete_and_deterministic() -> None:
    assert [path.name for path in sorted(MIGRATIONS.glob("*.sql"))] == EXPECTED_MIGRATIONS


def test_all_stage2_platform_tables_are_mapped_in_platform_schema() -> None:
    tables = (
        WorkspaceRecord, AssistantRecord, KnowledgeSourceRecord,
        ConversationRecord, MessageRecord,
    )
    assert {record.__table__.name for record in tables} == {
        "workspaces", "assistants", "knowledge_sources", "conversations", "messages",
    }
    assert {record.__table__.schema for record in tables} == {"platform"}


def test_migration_contains_complete_fk_graph_and_no_table_order_violation() -> None:
    sql = _migration_sql()
    assert "references platform.workspaces (id)" in sql
    assert "references platform.assistants (id)" in sql
    assert "references platform.conversations (id)" in sql
    assert sql.index("create table platform.workspaces") < sql.index(
        "create table platform.assistants"
    )
    assert sql.index("create table platform.assistants") < sql.index(
        "create table platform.conversations"
    )
    assert sql.index("create table platform.conversations") < sql.index(
        "create table platform.messages"
    )


def test_final_runtime_privilege_matrix_is_least_privilege() -> None:
    sql = " ".join(_migration_sql().split())
    expected = {
        "grant select, insert on table platform.workspaces": "knowledge_platform_runtime",
        "grant select, insert on table platform.assistants": "knowledge_platform_runtime",
        "grant select, insert, update on table platform.knowledge_sources": (
            "knowledge_platform_runtime"
        ),
        "grant select, insert on table platform.conversations": "knowledge_platform_runtime",
        "grant select, insert on table platform.messages": "knowledge_platform_runtime",
    }
    for grant, role in expected.items():
        assert f"{grant} to {role}" in sql
    assert "grant all" not in sql
    assert "grant delete" not in sql
    assert "grant update" not in sql
    assert " to public" not in sql
    assert " to anon" not in sql
    assert " to authenticated" not in sql


def test_all_runtime_tables_have_rls_and_force_rls() -> None:
    sql = _migration_sql()
    for table in ("workspaces", "assistants", "knowledge_sources", "conversations", "messages"):
        assert f"alter table platform.{table} enable row level security" in sql
        assert f"alter table platform.{table} force row level security" in sql


def test_cross_slice_regression_contracts_remain_present() -> None:
    sql = _migration_sql()
    assert "model_configuration jsonb not null" in sql
    assert "retrieval_configuration jsonb not null" in sql
    assert "lifecycle in (" in sql
    assert all(value in sql for value in (
        "'registered'", "'preparing'", "'ready'", "'disabled'",
        "'failed'", "'removing'", "'removed'",
    ))
    assert "primary key (conversation_id, sequence)" in sql
    assert "grant select, insert, update on table platform.knowledge_sources" in sql
    assert "grant select, insert on table platform.messages" in sql


def test_dependency_and_architecture_exclusions_remain_absent() -> None:
    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8").lower()
    for package in ("sentence-transformers", "torch", "transformers", "tokenizers", "safetensors"):
        assert package not in lock_text
    domain_root = ROOT / "src" / "knowledge_platform" / "modules"
    domain_text = "\n".join(
        path.read_text(encoding="utf-8") for path in domain_root.rglob("domain/*.py")
    )
    assert "import sqlalchemy" not in domain_text
    assert "import psycopg" not in domain_text
    assert "import pydantic_settings" not in domain_text
