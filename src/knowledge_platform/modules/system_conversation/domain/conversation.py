"""System-scoped conversations, separate from Workspace conversations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from knowledge_platform.modules.conversation.domain.roles import MessageRole


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

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("message sequence cannot be negative")
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be a MessageRole")
        if not self.content.strip():
            raise ValueError("message content is blank")
        if self.created_at.tzinfo is None:
            raise TypeError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SystemConversation:
    """A shared SYSTEM-scope aggregate; ``created_by`` is provenance only."""

    id: UUID
    title: str
    status: SystemConversationStatus
    created_by: UUID | None
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
    def create(cls, *, title: str, created_by: UUID | None) -> Self:
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            title=title,
            status=SystemConversationStatus.ACTIVE,
            created_by=created_by,
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
            messages=self.messages,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
            archived_at=None,
        )

    def append_message(self, *, role: MessageRole, content: str) -> Self:
        if self.status is SystemConversationStatus.ARCHIVED:
            raise ValueError("archived system conversation is read-only")
        now = datetime.now(UTC)
        message = SystemMessage(
            sequence=len(self.messages), role=role, content=content, created_at=now
        )
        return type(self)(
            id=self.id,
            title=self.title,
            status=self.status,
            created_by=self.created_by,
            messages=self.messages + (message,),
            created_at=self.created_at,
            updated_at=now,
            archived_at=self.archived_at,
        )
