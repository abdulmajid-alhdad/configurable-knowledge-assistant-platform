from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / (
    "20260829070000_assistant_knowledge_sources.sql"
)


def test_scope_insert_policy_enforces_parent_workspace_consistency() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create policy assistant_knowledge_sources_runtime_insert" in sql
    assert "a.workspace_id = assistant_knowledge_sources.workspace_id" in sql
    assert "s.workspace_id = assistant_knowledge_sources.workspace_id" in sql
    assert "a.id = assistant_knowledge_sources.assistant_id" in sql
    assert "s.id = assistant_knowledge_sources.knowledge_source_id" in sql
