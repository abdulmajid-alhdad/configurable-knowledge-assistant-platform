"""Workspace aggregate root."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from ._validation import required_text
from .identifiers import WorkspaceId


class WorkspaceOperationalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True, slots=True)
class Workspace:
    """A logical knowledge-project ownership boundary."""

    id: WorkspaceId
    name: str
    operational_status: WorkspaceOperationalStatus = WorkspaceOperationalStatus.ACTIVE
    ai_execution_enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, WorkspaceId):
            raise TypeError("id must be a WorkspaceId")
        object.__setattr__(self, "name", required_text(self.name, field="name"))
        if not isinstance(self.operational_status, WorkspaceOperationalStatus):
            raise TypeError("operational_status must be a WorkspaceOperationalStatus")
        if not isinstance(self.ai_execution_enabled, bool):
            raise TypeError("ai_execution_enabled must be a boolean")
        if (
            self.operational_status is WorkspaceOperationalStatus.SUSPENDED
            and self.ai_execution_enabled
        ):
            raise ValueError("a suspended workspace cannot enable AI execution")

    @classmethod
    def create(cls, *, name: str) -> Self:
        """Create a new workspace with a generated identity."""
        return cls(id=WorkspaceId.new(), name=name)

    def with_operational_state(
        self,
        *,
        status: WorkspaceOperationalStatus,
        ai_execution_enabled: bool,
    ) -> Self:
        """Return a validated operational-state replacement."""
        return type(self)(
            id=self.id,
            name=self.name,
            operational_status=status,
            ai_execution_enabled=(
                False
                if status is WorkspaceOperationalStatus.SUSPENDED
                else ai_execution_enabled
            ),
        )
