"""Workspace aggregate root."""

from dataclasses import dataclass
from typing import Self

from ._validation import required_text
from .identifiers import WorkspaceId


@dataclass(frozen=True, slots=True)
class Workspace:
    """A logical knowledge-project ownership boundary."""

    id: WorkspaceId
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, WorkspaceId):
            raise TypeError("id must be a WorkspaceId")
        object.__setattr__(self, "name", required_text(self.name, field="name"))

    @classmethod
    def create(cls, *, name: str) -> Self:
        """Create a new workspace with a generated identity."""
        return cls(id=WorkspaceId.new(), name=name)
