"""Durable Stage 6I-2 conversation outcome and evidence contracts."""

from pathlib import Path
from unittest.mock import MagicMock

from knowledge_platform.delivery.conversation_api import _conversation, create_conversation_router
from knowledge_platform.infrastructure.persistence.mappers import (
    conversation_from_records,
    conversation_to_record,
    message_evidence_to_records,
    message_to_record,
)
from knowledge_platform.infrastructure.persistence.models import ConversationRecord
from knowledge_platform.infrastructure.persistence.repositories import (
    ConversationRepository,
    MessageRepository,
)
from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.message import (
    MessageEvidence,
    MessageOutcome,
)
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / (
    "20260902010000_conversation_outcome_evidence.sql"
)


def _conversation_with_outcome(outcome: MessageOutcome) -> Conversation:
    conversation = Conversation.create_for_assistant(
        workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new()
    ).append_message(role=MessageRole.USER, content="question")
    evidence = (
        MessageEvidence(
            source_id=KnowledgeSourceId.new(),
            content="supporting content",
            provenance_locator="reference.json/1",
        ),
    ) if outcome is MessageOutcome.GROUNDED else ()
    return conversation.append_message(
        role=MessageRole.ASSISTANT,
        content="answer",
        outcome=outcome,
        evidence=evidence,
    )


def test_grounded_outcome_and_evidence_roundtrip_through_records() -> None:
    conversation = _conversation_with_outcome(MessageOutcome.GROUNDED)
    records = [message_to_record(conversation.id, item) for item in conversation.messages]
    evidence = message_evidence_to_records(conversation.id, conversation.messages[-1])

    restored = conversation_from_records(
        conversation_to_record(conversation), records, evidence
    )

    assert restored == conversation
    assert restored.messages[-1].outcome is MessageOutcome.GROUNDED
    assert restored.messages[-1].evidence[0].provenance_locator == "reference.json/1"


def test_grounded_message_is_flushed_before_its_evidence_is_added() -> None:
    conversation = _conversation_with_outcome(MessageOutcome.GROUNDED)
    session = MagicMock()

    MessageRepository(session).add(
        conversation, workspace_id=conversation.workspace_id
    )

    assert session.method_calls[0][0] == "add"
    assert session.method_calls[1][0] == "flush"
    assert session.method_calls[2][0] == "add_all"


def test_message_without_evidence_does_not_force_an_early_flush() -> None:
    conversation = _conversation_with_outcome(MessageOutcome.INSUFFICIENT_EVIDENCE)
    session = MagicMock()

    MessageRepository(session).add(
        conversation, workspace_id=conversation.workspace_id
    )

    session.flush.assert_not_called()
    session.add_all.assert_not_called()


def test_all_non_grounded_outcomes_reconstruct_without_evidence() -> None:
    for outcome in (
        MessageOutcome.INSUFFICIENT_EVIDENCE,
        MessageOutcome.POLICY_DENIED,
        MessageOutcome.TECHNICAL_FAILURE,
    ):
        conversation = _conversation_with_outcome(outcome)
        restored = conversation_from_records(
            conversation_to_record(conversation),
            [message_to_record(conversation.id, item) for item in conversation.messages],
        )
        assert restored.messages[-1].outcome is outcome
        assert restored.messages[-1].evidence == ()


def test_legacy_assistant_message_without_outcome_remains_readable() -> None:
    conversation = Conversation.create_for_assistant(
        workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new()
    ).append_message(role=MessageRole.ASSISTANT, content="legacy answer")
    restored = conversation_from_records(
        conversation_to_record(conversation),
        [message_to_record(conversation.id, conversation.messages[0])],
    )
    assert restored.messages[0].content == "legacy answer"
    assert restored.messages[0].outcome is None
    assert restored.messages[0].evidence == ()


def test_legacy_conversation_without_created_at_remains_readable() -> None:
    conversation = _conversation_with_outcome(MessageOutcome.GROUNDED)
    record = ConversationRecord(
        id=conversation.id.value,
        workspace_id=conversation.workspace_id.value,
        assistant_id=conversation.assistant_id.value,
        created_at=None,
    )

    restored = conversation_from_records(record, [])

    assert restored.created_at is None


def test_delivery_reconstructs_public_outcome_and_evidence_contract() -> None:
    conversation = _conversation_with_outcome(MessageOutcome.GROUNDED)
    response = _conversation(conversation)
    assistant_message = response.messages[-1]
    assert assistant_message["outcome"] == "GroundedAnswer"
    assert assistant_message["evidence"] == [{
        "source_id": str(conversation.messages[-1].evidence[0].source_id.value),
        "content": "supporting content",
        "provenance_locator": "reference.json/1",
    }]


def test_migration_is_normalized_append_only_and_workspace_isolated() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "add column outcome text null" in sql
    assert "add column created_at timestamptz null" in sql
    assert "alter column created_at set default now()" in sql
    assert "created_at timestamptz not null" not in sql
    assert "messages_assistant_outcome_only" in sql
    assert "create table platform.message_evidence" in sql
    assert "foreign key (conversation_id, message_sequence)" in sql
    assert "references platform.messages (conversation_id, sequence)" in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "current_setting('app.workspace_id', true)::uuid" in sql
    assert "source_id in (" in sql
    assert "grant select, insert" in sql
    assert "grant update" not in sql and "grant delete" not in sql


def test_conversation_listing_query_is_workspace_scoped_and_newest_first() -> None:
    session = MagicMock()
    session.scalars.return_value = iter([])
    workspace_id = WorkspaceId.new()

    result = ConversationRepository(session).list_for_workspace(
        workspace_id=workspace_id
    )

    assert result == []
    statement = str(session.scalars.call_args.args[0])
    assert "conversations.workspace_id" in statement
    assert "conversations.created_at DESC" in statement
    assert "NULLS LAST" in statement
    assert "conversations.id DESC" in statement


def test_assistant_filter_is_added_without_removing_workspace_scope() -> None:
    session = MagicMock()
    session.scalars.return_value = iter([])

    ConversationRepository(session).list_for_workspace(
        workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new()
    )

    statement = str(session.scalars.call_args.args[0])
    assert "conversations.workspace_id" in statement
    assert "conversations.assistant_id" in statement


def test_conversation_list_delivery_returns_real_summary_and_filter() -> None:
    conversation = _conversation_with_outcome(MessageOutcome.GROUNDED)

    class Services:
        received: tuple[object, object] | None = None

        def list_conversations(self, workspace_id, assistant_id=None):
            self.received = (workspace_id, assistant_id)
            return [conversation]

    services = Services()
    router = create_conversation_router(services)
    endpoint = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/workspaces/{workspace_id}/conversations"
    )

    result = endpoint(
        conversation.workspace_id.value, conversation.assistant_id.value
    )

    assert services.received == (
        conversation.workspace_id.value, conversation.assistant_id.value
    )
    assert result[0].id == conversation.id.value
    assert result[0].assistant_id == conversation.assistant_id.value
    assert result[0].message_count == 2
    assert result[0].last_message_preview == "answer"
    assert result[0].last_outcome == "GroundedAnswer"
