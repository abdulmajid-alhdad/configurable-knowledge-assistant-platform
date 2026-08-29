"""Static and unit contracts for the C2-04 persistence slice."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import ForeignKeyConstraint, PrimaryKeyConstraint

from knowledge_platform.infrastructure.persistence.mappers import (
    assistant_from_record,
    assistant_to_record,
    workspace_from_record,
    workspace_to_record,
)
from knowledge_platform.infrastructure.persistence.models import AssistantRecord, WorkspaceRecord
from knowledge_platform.infrastructure.persistence.payloads import ModelConfigurationPayload
from knowledge_platform.infrastructure.persistence.repositories import (
    AssistantRepository,
    WorkspaceRepository,
)
from knowledge_platform.infrastructure.persistence.workspace_context import (
    set_workspace_context,
    workspace_session_scope,
)
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260829020000_workspace_assistant_persistence.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def _policy_block(sql: str, policy: str) -> str:
    match = re.search(
        rf"create policy {policy}\b(?P<body>.*?)(?=\ncreate policy|\ngrant|\Z)",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group("body")


def test_workspace_mapping_preserves_domain_identity_and_fields() -> None:
    workspace = Workspace.create(name=" Workspace ")
    record = workspace_to_record(workspace)
    restored = workspace_from_record(record)
    assert restored == workspace


def test_assistant_mapping_preserves_domain_identity_and_fields() -> None:
    assistant = Assistant.create(
        workspace_id=WorkspaceId.new(),
        name="Assistant",
        description=None,
        instructions="Instructions",
        language="en",
        model_configuration=ModelConfiguration(provider="remote", model_reference="model"),
        retrieval_configuration=RetrievalConfiguration(),
    )
    restored = assistant_from_record(assistant_to_record(assistant))
    assert restored == assistant


def test_orm_tables_use_platform_schema_and_required_constraints() -> None:
    assert WorkspaceRecord.__table__.schema == "platform"
    assert AssistantRecord.__table__.schema == "platform"
    assert any(isinstance(c, PrimaryKeyConstraint) for c in AssistantRecord.__table__.constraints)
    assert any(isinstance(c, ForeignKeyConstraint) for c in AssistantRecord.__table__.constraints)
    assert AssistantRecord.__table__.c.workspace_id.nullable is False
    assert str(AssistantRecord.__table__.c.model_configuration.type) == "JSONB"
    assert str(AssistantRecord.__table__.c.retrieval_configuration.type) == "JSONB"


def test_workspace_context_uses_parameterized_transaction_local_set_config() -> None:
    session = MagicMock()
    set_workspace_context(session, WorkspaceId.new())
    statement = session.execute.call_args.args[0]
    assert ":workspace_id" in str(statement)
    assert "set_config" in str(statement)
    assert session.execute.call_args.args[1]["workspace_id"]
    assert "true" in str(statement)


def test_workspace_session_scope_sets_context_before_yield_and_propagates_failure() -> None:
    factory = MagicMock()
    session = MagicMock()
    factory.begin.return_value.__enter__.return_value = session

    with pytest.raises(RuntimeError, match="boom"):
        with workspace_session_scope(factory, WorkspaceId.new()) as yielded:
            assert yielded is session
            assert session.execute.called
            raise RuntimeError("boom")

    factory.begin.assert_called_once_with()
    factory.begin.return_value.__exit__.assert_called_once()


def test_workspace_repository_add_and_get_do_not_commit_or_close() -> None:
    session = MagicMock()
    repository = WorkspaceRepository(session)
    workspace = Workspace.create(name="Workspace")
    repository.add(workspace)
    session.get.return_value = workspace_to_record(workspace)

    assert repository.get(workspace.id) == workspace
    session.commit.assert_not_called()
    session.close.assert_not_called()


def test_assistant_repository_add_checks_workspace_and_get_filters_both_ids() -> None:
    session = MagicMock()
    repository = AssistantRepository(session)
    workspace_id = WorkspaceId.new()
    assistant = Assistant.create(
        workspace_id=workspace_id,
        name="Assistant",
        description=None,
        instructions="Instructions",
        language="en",
        model_configuration=ModelConfiguration(provider="remote", model_reference="model"),
        retrieval_configuration=RetrievalConfiguration(),
    )

    repository.add(assistant, workspace_id=workspace_id)
    with pytest.raises(ValueError):
        repository.add(assistant, workspace_id=WorkspaceId.new())
    session.scalar.return_value = assistant_to_record(assistant)

    assert repository.get(assistant_id=assistant.id, workspace_id=workspace_id) == assistant
    statement = session.scalar.call_args.args[0]
    assert "assistants.id" in str(statement)
    assert "assistants.workspace_id" in str(statement)
    session.commit.assert_not_called()
    session.close.assert_not_called()


def test_malformed_model_configuration_payload_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelConfigurationPayload.model_validate({"provider": "remote", "unexpected": "x"})


def test_migration_defines_workspace_assistant_security_boundary() -> None:
    sql = _sql()
    assert "create table platform.workspaces" in sql
    assert "create table platform.assistants" in sql
    assert "references platform.workspaces (id)" in sql
    assert sql.count("enable row level security") == 2
    assert sql.count("force row level security") == 2
    workspace_context = "current_setting('app.workspace_id', true)::uuid"
    policies = (
        ("workspaces_runtime_select", "for select", f"using (id = {workspace_context})"),
        ("workspaces_runtime_insert", "for insert", f"with check (id = {workspace_context})"),
        ("workspaces_runtime_update", "for update", f"using (id = {workspace_context})"),
        ("workspaces_runtime_update", "for update", f"with check (id = {workspace_context})"),
        ("workspaces_runtime_delete", "for delete", f"using (id = {workspace_context})"),
        (
            "assistants_runtime_select",
            "for select",
            f"using (workspace_id = {workspace_context})",
        ),
        (
            "assistants_runtime_insert",
            "for insert",
            f"with check (workspace_id = {workspace_context})",
        ),
        (
            "assistants_runtime_update",
            "for update",
            f"using (workspace_id = {workspace_context})",
        ),
        (
            "assistants_runtime_update",
            "for update",
            f"with check (workspace_id = {workspace_context})",
        ),
        (
            "assistants_runtime_delete",
            "for delete",
            f"using (workspace_id = {workspace_context})",
        ),
    )
    for policy, operation, clause in policies:
        block = _policy_block(sql, policy)
        assert operation in block
        assert clause in block
    assert "grant all" not in sql
    assert " to public" not in sql
    assert " to anon" not in sql
    assert " to authenticated" not in sql
    assert "owner to knowledge_platform_runtime" not in sql
    assert "grant select, insert on table platform.workspaces" in sql
    assert "grant select, insert on table platform.assistants" in sql
    assert "grant select, insert, update, delete" not in sql
