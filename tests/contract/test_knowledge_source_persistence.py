"""Static and unit contracts for KnowledgeSource persistence."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import ForeignKeyConstraint, PrimaryKeyConstraint

from knowledge_platform.infrastructure.persistence.mappers import (
    knowledge_source_from_record,
    knowledge_source_to_record,
)
from knowledge_platform.infrastructure.persistence.models import KnowledgeSourceRecord
from knowledge_platform.infrastructure.persistence.repositories import KnowledgeSourceRepository
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
    KnowledgeSourceLifecycle,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / (
    "20260829030000_knowledge_source_lifecycle_persistence.sql"
)


def _source(workspace_id: WorkspaceId | None = None) -> KnowledgeSource:
    return KnowledgeSource.create(
        workspace_id=workspace_id or WorkspaceId.new(),
        name="Reference source",
        kind=KnowledgeSourceKind.DOCUMENT,
    )


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def _policy_block(sql: str, name: str) -> str:
    start = sql.index(f"create policy {name}")
    end = sql.find("\ncreate policy", start + 1)
    if end == -1:
        end = sql.find("\ngrant", start + 1)
    return sql[start:end]


def test_knowledge_source_mapper_roundtrips_all_domain_fields_and_lifecycle() -> None:
    source = _source().begin_preparation().mark_ready()
    restored = knowledge_source_from_record(knowledge_source_to_record(source))
    assert restored == source
    assert knowledge_source_to_record(source).lifecycle == "ready"


@pytest.mark.parametrize("state", list(KnowledgeSourceLifecycle))
def test_mapper_roundtrips_every_lifecycle_state(state: KnowledgeSourceLifecycle) -> None:
    source = KnowledgeSource(
        id=KnowledgeSourceId.new(),
        workspace_id=WorkspaceId.new(),
        name="Source",
        kind=KnowledgeSourceKind.STRUCTURED,
        lifecycle=state,
    )
    assert knowledge_source_from_record(knowledge_source_to_record(source)) == source


def test_invalid_persisted_lifecycle_fails_explicitly() -> None:
    record = MagicMock(
        id=KnowledgeSourceId.new().value,
        workspace_id=WorkspaceId.new().value,
        name="Source",
        kind="document",
        lifecycle="NOT_A_STATE",
    )
    with pytest.raises(ValueError):
        knowledge_source_from_record(record)


def test_invalid_persisted_kind_fails_explicitly() -> None:
    record = MagicMock(
        id=KnowledgeSourceId.new().value,
        workspace_id=WorkspaceId.new().value,
        name="Source",
        kind="unsupported_kind",
        lifecycle="registered",
    )
    with pytest.raises(ValueError):
        knowledge_source_from_record(record)


def test_orm_metadata_has_platform_uuid_fk_and_required_columns() -> None:
    table = KnowledgeSourceRecord.__table__
    assert table.schema == "platform"
    assert any(isinstance(c, PrimaryKeyConstraint) for c in table.constraints)
    assert any(isinstance(c, ForeignKeyConstraint) for c in table.constraints)
    assert table.c.workspace_id.nullable is False
    assert table.c.name.nullable is False
    assert table.c.kind.nullable is False
    assert table.c.lifecycle.nullable is False
    assert {column.name for column in table.columns} == {
        "id", "workspace_id", "name", "kind", "lifecycle",
    }


def test_repository_enforces_workspace_and_scopes_reads_and_transitions() -> None:
    session = MagicMock()
    repository = KnowledgeSourceRepository(session)
    workspace_id = WorkspaceId.new()
    source = _source(workspace_id)
    repository.add(source, workspace_id=workspace_id)
    with pytest.raises(ValueError):
        repository.add(source, workspace_id=WorkspaceId.new())
    session.scalar.return_value = knowledge_source_to_record(source)
    assert repository.get(source_id=source.id, workspace_id=workspace_id) == source
    statement = session.scalar.call_args.args[0]
    assert "knowledge_sources.id" in str(statement)
    assert "knowledge_sources.workspace_id" in str(statement)
    transitioned = source.begin_preparation()
    result = MagicMock(rowcount=1)
    session.execute.return_value = result
    repository.save_transition(
        previous=source,
        transitioned=transitioned,
        workspace_id=workspace_id,
    )
    statement = session.execute.call_args.args[0]
    rendered = str(statement)
    assert "knowledge_sources.id" in rendered
    assert "knowledge_sources.workspace_id" in rendered
    assert "knowledge_sources.lifecycle" in rendered
    assert "name" not in rendered.split("SET", 1)[-1]
    assert "kind" not in rendered.split("SET", 1)[-1]
    with pytest.raises(ValueError):
        repository.save_transition(
            previous=source,
            transitioned=transitioned,
            workspace_id=WorkspaceId.new(),
        )
    session.commit.assert_not_called()
    session.close.assert_not_called()
    assert not hasattr(repository, "delete")


@pytest.mark.parametrize(
    ("before", "operation"),
    [
        (KnowledgeSourceLifecycle.REGISTERED, "begin_preparation"),
        (KnowledgeSourceLifecycle.PREPARING, "mark_ready"),
        (KnowledgeSourceLifecycle.PREPARING, "mark_failed"),
        (KnowledgeSourceLifecycle.FAILED, "begin_preparation"),
        (KnowledgeSourceLifecycle.READY, "disable"),
        (KnowledgeSourceLifecycle.DISABLED, "enable"),
        (KnowledgeSourceLifecycle.READY, "begin_removal"),
        (KnowledgeSourceLifecycle.DISABLED, "begin_removal"),
        (KnowledgeSourceLifecycle.REMOVING, "mark_removed"),
    ],
)
def test_save_transition_accepts_each_domain_transition(
    before: KnowledgeSourceLifecycle, operation: str,
) -> None:
    workspace_id = WorkspaceId.new()
    previous = KnowledgeSource(
        id=KnowledgeSourceId.new(), workspace_id=workspace_id, name="Source",
        kind=KnowledgeSourceKind.DOCUMENT, lifecycle=before,
    )
    transitioned = getattr(previous, operation)()
    session = MagicMock()
    session.execute.return_value = MagicMock(rowcount=1)
    KnowledgeSourceRepository(session).save_transition(
        previous=previous, transitioned=transitioned, workspace_id=workspace_id,
    )


@pytest.mark.parametrize("before,after", [
    (KnowledgeSourceLifecycle.REGISTERED, KnowledgeSourceLifecycle.READY),
    (KnowledgeSourceLifecycle.FAILED, KnowledgeSourceLifecycle.READY),
    (KnowledgeSourceLifecycle.DISABLED, KnowledgeSourceLifecycle.PREPARING),
    (KnowledgeSourceLifecycle.REMOVED, KnowledgeSourceLifecycle.READY),
    (KnowledgeSourceLifecycle.READY, KnowledgeSourceLifecycle.READY),
])
def test_save_transition_rejects_invalid_domain_pairs(
    before: KnowledgeSourceLifecycle, after: KnowledgeSourceLifecycle,
) -> None:
    workspace_id = WorkspaceId.new()
    previous = KnowledgeSource(
        id=KnowledgeSourceId.new(), workspace_id=workspace_id, name="Source",
        kind=KnowledgeSourceKind.DOCUMENT, lifecycle=before,
    )
    transitioned = KnowledgeSource(
        id=previous.id, workspace_id=workspace_id, name="Source",
        kind=KnowledgeSourceKind.DOCUMENT, lifecycle=after,
    )
    session = MagicMock()
    with pytest.raises(ValueError):
        KnowledgeSourceRepository(session).save_transition(
            previous=previous, transitioned=transitioned, workspace_id=workspace_id,
        )
    session.execute.assert_not_called()


def test_save_transition_rejects_identity_name_and_kind_changes_and_stale_update() -> None:
    workspace_id = WorkspaceId.new()
    previous = _source(workspace_id)
    transitioned = previous.begin_preparation()
    session = MagicMock()
    repository = KnowledgeSourceRepository(session)
    with pytest.raises(ValueError):
        repository.save_transition(
            previous=previous,
            transitioned=KnowledgeSource(
                id=KnowledgeSourceId.new(), workspace_id=workspace_id, name=previous.name,
                kind=previous.kind, lifecycle=transitioned.lifecycle,
            ),
            workspace_id=workspace_id,
        )
    with pytest.raises(ValueError):
        repository.save_transition(
            previous=previous,
            transitioned=KnowledgeSource(
                id=previous.id, workspace_id=workspace_id, name="Changed",
                kind=previous.kind, lifecycle=transitioned.lifecycle,
            ),
            workspace_id=workspace_id,
        )
    with pytest.raises(ValueError):
        repository.save_transition(
            previous=previous,
            transitioned=KnowledgeSource(
                id=previous.id, workspace_id=workspace_id, name=previous.name,
                kind=KnowledgeSourceKind.STRUCTURED, lifecycle=transitioned.lifecycle,
            ),
            workspace_id=workspace_id,
        )
    session.execute.return_value = MagicMock(rowcount=0)
    with pytest.raises(RuntimeError, match="conflict"):
        repository.save_transition(
            previous=previous, transitioned=transitioned, workspace_id=workspace_id,
        )


def test_domain_has_no_persistence_framework_imports() -> None:
    domain_root = Path(__file__).resolve().parents[2] / "src" / "knowledge_platform" / "domain"
    assert not domain_root.exists()
    knowledge_domain = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "knowledge_platform"
        / "modules"
        / "knowledge_sources"
        / "domain"
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in knowledge_domain.glob("*.py"))
    assert "sqlalchemy" not in source
    assert "psycopg" not in source
    assert "pydantic_settings" not in source


def test_migration_defines_exact_lifecycle_rls_and_least_privilege() -> None:
    sql = _sql()
    assert "create table platform.knowledge_sources" in sql
    assert "references platform.workspaces (id)" in sql
    assert "lifecycle in (" in sql
    assert all(state in sql for state in (
        "'registered'", "'preparing'", "'ready'", "'disabled'",
        "'failed'", "'removing'", "'removed'",
    ))
    assert "enable row level security" in sql
    assert "force row level security" in sql
    context = "current_setting('app.workspace_id', true)::uuid"
    checks = {
        "knowledge_sources_runtime_select": f"using (workspace_id = {context})",
        "knowledge_sources_runtime_insert": f"with check (workspace_id = {context})",
        "knowledge_sources_runtime_update": f"using (workspace_id = {context})",
        "knowledge_sources_runtime_delete": f"using (workspace_id = {context})",
    }
    for name, clause in checks.items():
        assert clause in _policy_block(sql, name)
    assert _policy_block(sql, "knowledge_sources_runtime_update").count(
        f"with check (workspace_id = {context})"
    ) == 1
    assert "grant select, insert, update on table platform.knowledge_sources" in sql
    assert "grant all" not in sql
    assert " to public" not in sql
    assert " to anon" not in sql
    assert " to authenticated" not in sql
    assert "grant delete" not in sql
    assert "create policy" in sql
