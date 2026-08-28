"""Typed identities owned by the workspace assistant domain."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class WorkspaceId:
    """Identity of a workspace."""

    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class AssistantId:
    """Identity of an assistant."""

    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)
