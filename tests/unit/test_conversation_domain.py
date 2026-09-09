"""Unit tests for the Conversation domain contract."""

from dataclasses import FrozenInstanceError, fields
from typing import cast

import pytest

from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.conversation.domain.message import Message
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


def conversation() -> Conversation:
    return Conversation.create_for_assistant(
        workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new()
    )


def test_message_roles_are_exact() -> None:
    assert {role.value for role in MessageRole} == {"user", "assistant"}


def test_message_validates_and_normalizes_content() -> None:
    message = Message(sequence=0, role=MessageRole.USER, content=" Hello ")
    assert message.content == "Hello"
    with pytest.raises(FrozenInstanceError):
        message.__setattr__("content", "Changed")


@pytest.mark.parametrize("sequence", [-1, -2])
def test_message_rejects_negative_sequence(sequence: int) -> None:
    with pytest.raises(ValueError):
        Message(sequence=sequence, role=MessageRole.USER, content="x")


@pytest.mark.parametrize("sequence", [True, "0"])
def test_message_rejects_invalid_sequence_type(sequence: object) -> None:
    with pytest.raises(TypeError):
        Message(sequence=cast(int, sequence), role=MessageRole.USER, content="x")


def test_message_rejects_invalid_role_and_blank_content() -> None:
    with pytest.raises(TypeError):
        Message(sequence=0, role=cast(MessageRole, "user"), content="x")
    with pytest.raises(ValueError):
        Message(sequence=0, role=MessageRole.USER, content=" \t")


def test_conversation_factory_initializes_identity_and_empty_messages() -> None:
    created = conversation()
    assert isinstance(created.id, ConversationId)
    assert created.messages == ()


def test_append_is_immutable_ordered_and_preserves_identity() -> None:
    original = conversation()
    first = original.append_message(role=MessageRole.USER, content="Hi")
    second = first.append_message(role=MessageRole.ASSISTANT, content="Hello")
    assert original.messages == ()
    assert [message.sequence for message in second.messages] == [0, 1]
    assert [message.role for message in second.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert [message.content for message in second.messages] == ["Hi", "Hello"]
    assert (second.id, second.workspace_id, second.assistant_id) == (
        original.id, original.workspace_id, original.assistant_id
    )


def test_context_returns_latest_messages_in_chronological_order() -> None:
    current = conversation()
    for content in ("one", "two", "three"):
        current = current.append_message(role=MessageRole.USER, content=content)
    assert [message.content for message in current.context(max_messages=2)] == ["two", "three"]
    assert current.context(max_messages=10) == current.messages


@pytest.mark.parametrize("limit", [0, -1, True, "2"])
def test_context_rejects_invalid_limits(limit: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        conversation().context(max_messages=cast(int, limit))


def test_conversation_shape_includes_only_approved_lifecycle_state() -> None:
    assert {field.name for field in fields(Conversation)} == {
        "id",
        "workspace_id",
        "assistant_id",
        "title",
        "status",
        "messages",
        "created_at",
        "updated_at",
        "archived_at",
    }
