"""Unit tests for UUID-backed domain identifiers."""

from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.evaluation.domain.identifiers import EvaluationRunId
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

Identifier = WorkspaceId | AssistantId | KnowledgeSourceId | ConversationId | EvaluationRunId
IDENTIFIER_TYPES: tuple[type[Identifier], ...] = (
    WorkspaceId,
    AssistantId,
    KnowledgeSourceId,
    ConversationId,
    EvaluationRunId,
)


def test_new_identifiers_have_the_expected_type_and_unique_uuid_values() -> None:
    for identifier_type in IDENTIFIER_TYPES:
        first = identifier_type.new()
        second = identifier_type.new()

        assert type(first) is identifier_type
        assert isinstance(first.value, UUID)
        assert first != second
        assert str(first) == str(first.value)


def test_identifiers_with_the_same_type_and_uuid_are_equal_and_hashable() -> None:
    value = uuid4()

    for identifier_type in IDENTIFIER_TYPES:
        first = identifier_type(value)
        second = identifier_type(value)

        assert first == second
        assert hash(first) == hash(second)
        assert {first, second} == {first}


def test_identifier_types_remain_distinct_at_runtime() -> None:
    value = uuid4()
    identifiers = [identifier_type(value) for identifier_type in IDENTIFIER_TYPES]

    assert len({type(identifier) for identifier in identifiers}) == len(IDENTIFIER_TYPES)


def test_identifiers_are_immutable() -> None:
    identifier = WorkspaceId.new()

    with pytest.raises(FrozenInstanceError):
        identifier.__setattr__("value", uuid4())


@given(value=st.uuids())
def test_identifier_construction_preserves_arbitrary_uuid_values(value: UUID) -> None:
    for identifier_type in IDENTIFIER_TYPES:
        identifier = identifier_type(value)

        assert identifier.value == value
        assert str(identifier) == str(value)
