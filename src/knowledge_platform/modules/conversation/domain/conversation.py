"""Conversation aggregate and immutable message operations."""

from dataclasses import dataclass
from typing import Self

from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

from .identifiers import ConversationId
from .message import Message
from .roles import MessageRole


@dataclass(frozen=True, slots=True)
class Conversation:
    id: ConversationId
    workspace_id: WorkspaceId
    assistant_id: AssistantId
    messages: tuple[Message, ...]

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

    @classmethod
    def create_for_assistant(
        cls,
        *,
        workspace_id: WorkspaceId,
        assistant_id: AssistantId,
    ) -> Self:
        return cls(
            id=ConversationId.new(),
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            messages=(),
        )

    def append_message(self, *, role: MessageRole, content: str) -> Self:
        sequence = self.messages[-1].sequence + 1 if self.messages else 0
        return type(self)(
            id=self.id,
            workspace_id=self.workspace_id,
            assistant_id=self.assistant_id,
            messages=self.messages + (Message(sequence=sequence, role=role, content=content),),
        )

    def context(self, *, max_messages: int) -> tuple[Message, ...]:
        if isinstance(max_messages, bool) or not isinstance(max_messages, int):
            raise TypeError("max_messages must be an integer")
        if max_messages <= 0:
            raise ValueError("max_messages must be greater than zero")
        return self.messages[-max_messages:]
