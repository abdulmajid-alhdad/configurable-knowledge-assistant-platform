"""Typed identities owned by the knowledge sources domain."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class KnowledgeSourceId:
    """Identity of a knowledge source."""

    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)
