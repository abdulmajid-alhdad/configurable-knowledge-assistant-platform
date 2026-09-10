"""System-scoped conversations, separate from Workspace conversations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from knowledge_platform.modules.conversation.domain.message import (
    MessageEvidence,
    MessageOutcome,
)
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


class SystemConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


def _title(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("system conversation title is blank")
    if len(normalized) > 200:
        raise ValueError("system conversation title is too long")
    return normalized


@dataclass(frozen=True, slots=True)
class SystemMessage:
    sequence: int
    role: MessageRole
    content: str
    created_at: datetime
    outcome: MessageOutcome | None = None
    evidence: tuple[MessageEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("message sequence cannot be negative")
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be a MessageRole")
        if not self.content.strip():
            raise ValueError("message content is blank")
        if self.created_at.tzinfo is None:
            raise TypeError("created_at must be timezone-aware")
        if self.outcome is not None and not isinstance(self.outcome, MessageOutcome):
            raise TypeError("outcome must be a MessageOutcome when provided")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, MessageEvidence) for item in self.evidence
        ):
            raise TypeError("evidence must contain only MessageEvidence values")
        if self.role is MessageRole.USER and (self.outcome is not None or self.evidence):
            raise ValueError("user messages cannot carry assistant outcomes")
        if self.outcome is MessageOutcome.GROUNDED and not self.evidence:
            raise ValueError("grounded messages require evidence")
        if self.outcome is not MessageOutcome.GROUNDED and self.evidence:
            raise ValueError("only grounded messages may carry evidence")


@dataclass(frozen=True, slots=True)
class SystemConversation:
    """A shared SYSTEM-scope aggregate; ``created_by`` is provenance only."""

    id: UUID
    title: str
    status: SystemConversationStatus
    created_by: UUID | None
    workspace_id: WorkspaceId | None
    assistant_id: AssistantId | None
    messages: tuple[SystemMessage, ...]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")
        object.__setattr__(self, "title", _title(self.title))
        if not isinstance(self.status, SystemConversationStatus):
            raise TypeError("status must be a SystemConversationStatus")
        if (self.workspace_id is None) != (self.assistant_id is None):
            raise ValueError("system conversation binding must be complete or absent")
        if self.workspace_id is not None and not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId when bound")
        if self.assistant_id is not None and not isinstance(self.assistant_id, AssistantId):
            raise TypeError("assistant_id must be an AssistantId when bound")
        if not isinstance(self.messages, tuple) or not all(
            isinstance(message, SystemMessage) for message in self.messages
        ):
            raise TypeError("messages must be SystemMessage values")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise TypeError("timestamps must be timezone-aware")
        if self.status is SystemConversationStatus.ACTIVE and self.archived_at is not None:
            raise ValueError("active system conversation cannot have archived_at")
        if self.status is SystemConversationStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived system conversation requires archived_at")

    @classmethod
    def create(
        cls,
        *,
        title: str,
        created_by: UUID | None,
        workspace_id: WorkspaceId,
        assistant_id: AssistantId,
    ) -> Self:
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            title=title,
            status=SystemConversationStatus.ACTIVE,
            created_by=created_by,
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            messages=(),
            created_at=now,
            updated_at=now,
        )

    def rename(self, title: str) -> Self:
        return type(self)(
            id=self.id,
            title=title,
            status=self.status,
            created_by=self.created_by,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
            archived_at=self.archived_at,
        )

    def archive(self) -> Self:
        now = datetime.now(UTC)
        return type(self)(
            id=self.id,
            title=self.title,
            status=SystemConversationStatus.ARCHIVED,
            created_by=self.created_by,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages,
            created_at=self.created_at,
            updated_at=now,
            archived_at=now,
        )

    def restore(self) -> Self:
        return type(self)(
            id=self.id,
            title=self.title,
            status=SystemConversationStatus.ACTIVE,
            created_by=self.created_by,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
            archived_at=None,
        )

    @property
    def is_bound(self) -> bool:
        return self.workspace_id is not None and self.assistant_id is not None

    def append_message(
        self,
        *,
        role: MessageRole,
        content: str,
        outcome: MessageOutcome | None = None,
        evidence: tuple[MessageEvidence, ...] = (),
    ) -> Self:
        if self.status is SystemConversationStatus.ARCHIVED:
            raise ValueError("archived system conversation is read-only")
        now = datetime.now(UTC)
        message = SystemMessage(
            sequence=len(self.messages),
            role=role,
            content=content,
            created_at=now,
            outcome=outcome,
            evidence=evidence,
        )
        return type(self)(
            id=self.id,
            title=self.title,
            status=self.status,
            created_by=self.created_by,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages + (message,),
            created_at=self.created_at,
            updated_at=now,
            archived_at=self.archived_at,
        )
