"""Typed identities owned by the conversation domain."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ConversationId:
    """Identity of a conversation."""

    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)
