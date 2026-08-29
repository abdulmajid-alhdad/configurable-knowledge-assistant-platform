"""Static and unit contracts for C2-06 conversation persistence."""

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import ForeignKeyConstraint, PrimaryKeyConstraint

from knowledge_platform.infrastructure.persistence.mappers import (
    conversation_from_records,
    conversation_to_record,
    message_to_record,
)
from knowledge_platform.infrastructure.persistence.models import ConversationRecord, MessageRecord
from knowledge_platform.infrastructure.persistence.repositories import (
    ConversationRepository,
    MessageRepository,
)
from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / (
    "20260829040000_conversation_messages_persistence.sql"
)


def _conversation() -> Conversation:
    return Conversation.create_for_assistant(
        workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new()
    )


def test_conversation_and_message_mapper_roundtrip_preserves_order_and_values() -> None:
    conversation = _conversation().append_message(role=MessageRole.USER, content=" Hi ")
    conversation = conversation.append_message(role=MessageRole.ASSISTANT, content="Hello")
    record = conversation_to_record(conversation)
    messages = [message_to_record(conversation.id, message) for message in conversation.messages]
    restored = conversation_from_records(record, list(reversed(messages)))
    assert restored == conversation


def test_orm_metadata_uses_platform_schema_uuid_keys_and_foreign_keys() -> None:
    assert ConversationRecord.__table__.schema == "platform"
    assert MessageRecord.__table__.schema == "platform"
    assert any(isinstance(c, PrimaryKeyConstraint) for c in MessageRecord.__table__.constraints)
    assert any(
        isinstance(c, ForeignKeyConstraint) for c in ConversationRecord.__table__.constraints
    )
    assert any(isinstance(c, ForeignKeyConstraint) for c in MessageRecord.__table__.constraints)


def test_repositories_validate_workspace_and_do_not_own_transactions() -> None:
    session = MagicMock()
    conversation = _conversation().append_message(role=MessageRole.USER, content="Hi")
    ConversationRepository(session).add(conversation, workspace_id=conversation.workspace_id)
    MessageRepository(session).add(conversation, workspace_id=conversation.workspace_id)
    with pytest.raises(ValueError):
        MessageRepository(session).add(conversation, workspace_id=WorkspaceId.new())
    session.commit.assert_not_called()
    session.close.assert_not_called()
    assert not hasattr(MessageRepository(session), "delete")


def test_conversation_repository_get_scopes_workspace_and_message_query() -> None:
    session = MagicMock()
    conversation = _conversation()
    session.scalar.return_value = conversation_to_record(conversation)
    session.scalars.return_value = iter([])
    restored = ConversationRepository(session).get(
        conversation_id=conversation.id, workspace_id=conversation.workspace_id
    )
    assert restored == conversation
    assert "conversations.id" in str(session.scalar.call_args.args[0])
    assert "conversations.workspace_id" in str(session.scalar.call_args.args[0])


def test_migration_contains_workspace_rls_and_append_only_grants() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table platform.conversations" in sql
    assert "create table platform.messages" in sql
    assert "references platform.workspaces (id)" in sql
    assert "references platform.assistants (id)" in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "grant select, insert on table platform.conversations" in sql
    assert "grant select, insert on table platform.messages" in sql
    assert "grant update" not in sql and "grant delete" not in sql
    assert "grant all" not in sql
    assert " to public" not in sql and " to anon" not in sql and " to authenticated" not in sql
    assert "current_setting('app.workspace_id', true)::uuid" in sql
    assert "metadata.create_all" not in sql
    def policy_block(name: str) -> str:
        match = re.search(
            rf"create policy {name}\b(?P<body>.*?)(?=\ncreate policy|\ngrant|\Z)",
            sql,
            flags=re.DOTALL,
        )
        assert match is not None
        return match.group("body")
    context = "current_setting('app.workspace_id', true)::uuid"
    assert "for select" in policy_block("conversations_runtime_select")
    assert f"using (workspace_id = {context})" in policy_block("conversations_runtime_select")
    assert "for insert" in policy_block("conversations_runtime_insert")
    assert f"with check (workspace_id = {context})" in policy_block("conversations_runtime_insert")
    for name in ("messages_runtime_select", "messages_runtime_insert"):
        block = policy_block(name)
        assert "conversation_id in (" in block
        assert f"workspace_id = {context}" in block
