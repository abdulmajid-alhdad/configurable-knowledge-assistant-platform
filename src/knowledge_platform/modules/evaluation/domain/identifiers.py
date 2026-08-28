"""Typed identities owned by the evaluation domain."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EvaluationRunId:
    """Identity of an evaluation run."""

    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)
