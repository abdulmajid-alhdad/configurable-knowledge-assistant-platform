"""Conversation aggregate and immutable message operations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

from .identifiers import ConversationId
from .message import Message, MessageEvidence, MessageOutcome
from .roles import MessageRole


class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


def _conversation_title(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("conversation title is blank")
    if len(normalized) > 200:
        raise ValueError("conversation title is too long")
    return normalized


@dataclass(frozen=True, slots=True)
class Conversation:
    id: ConversationId
    workspace_id: WorkspaceId
    assistant_id: AssistantId
    messages: tuple[Message, ...]
    created_at: datetime | None
    title: str = "Untitled conversation"
    status: ConversationStatus = ConversationStatus.ACTIVE
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ConversationId):
            raise TypeError("id must be a ConversationId")
        if not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        if not isinstance(self.assistant_id, AssistantId):
            raise TypeError("assistant_id must be an AssistantId")
        if not isinstance(self.messages, tuple):
            raise TypeError("messages must be a tuple")
        if not all(isinstance(message, Message) for message in self.messages):
            raise TypeError("messages must contain only Message values")
        if self.created_at is not None and (
            not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None
        ):
            raise TypeError("created_at must be a timezone-aware datetime")
        object.__setattr__(self, "title", _conversation_title(self.title))
        if not isinstance(self.status, ConversationStatus):
            raise TypeError("status must be a ConversationStatus")
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            raise TypeError("updated_at must be timezone-aware")
        if self.status is ConversationStatus.ACTIVE and self.archived_at is not None:
            raise ValueError("active conversation cannot have archived_at")
        if self.status is ConversationStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived conversation requires archived_at")

    @classmethod
    def create_for_assistant(
        cls,
        *,
        workspace_id: WorkspaceId,
        assistant_id: AssistantId,
        title: str = "Untitled conversation",
    ) -> Self:
        now = datetime.now(UTC)
        return cls(
            id=ConversationId.new(),
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            messages=(),
            created_at=now,
            title=title,
            status=ConversationStatus.ACTIVE,
            updated_at=now,
        )

    def rename(self, title: str) -> Self:
        return type(self)(
            id=self.id,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages,
            created_at=self.created_at,
            title=title,
            status=self.status,
            updated_at=datetime.now(UTC),
            archived_at=self.archived_at,
        )

    def archive(self) -> Self:
        now = datetime.now(UTC)
        return type(self)(
            id=self.id,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages,
            created_at=self.created_at,
            title=self.title,
            status=ConversationStatus.ARCHIVED,
            updated_at=now,
            archived_at=now,
        )

    def restore(self) -> Self:
        return type(self)(
            id=self.id,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages,
            created_at=self.created_at,
            title=self.title,
            status=ConversationStatus.ACTIVE,
            updated_at=datetime.now(UTC),
            archived_at=None,
        )

    def append_message(
        self, *, role: MessageRole, content: str,
        outcome: MessageOutcome | None = None,
        evidence: tuple[MessageEvidence, ...] = (),
    ) -> Self:
        if self.status is ConversationStatus.ARCHIVED:
            raise ValueError("archived conversation is read-only")
        sequence = self.messages[-1].sequence + 1 if self.messages else 0
        return type(self)(
            id=self.id,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages + (
                Message(
                    sequence=sequence, role=role, content=content,
                    outcome=outcome, evidence=evidence,
                ),
            ),
            created_at=self.created_at,
            title=self.title,
            status=self.status,
            updated_at=datetime.now(UTC),
            archived_at=self.archived_at,
        )

    def context(self, *, max_messages: int) -> tuple[Message, ...]:
        if isinstance(max_messages, bool) or not isinstance(max_messages, int):
            raise TypeError("max_messages must be an integer")
        if max_messages <= 0:
            raise ValueError("max_messages must be greater than zero")
        return self.messages[-max_messages:]
