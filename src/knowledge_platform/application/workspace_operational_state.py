"""Application contract for authoritative Workspace operational state."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from knowledge_platform.modules.workspace_assistant.domain.workspace import (
    WorkspaceOperationalStatus,
)


class WorkspaceOperationalError(RuntimeError):
    """Stable base for operational-state denial."""


class WorkspaceSuspended(WorkspaceOperationalError):
    pass


class WorkspaceAIExecutionDisabled(WorkspaceOperationalError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceOperationalState:
    workspace_id: UUID
    status: WorkspaceOperationalStatus
    ai_execution_enabled: bool

    @property
    def permits_ai_execution(self) -> bool:
        return (
            self.status is WorkspaceOperationalStatus.ACTIVE
            and self.ai_execution_enabled
        )


class WorkspaceOperationalStatePort(Protocol):
    def get(self, user_id: UUID, workspace_id: UUID) -> WorkspaceOperationalState: ...

    def require_active(self, user_id: UUID, workspace_id: UUID) -> None: ...

    def require_ai_execution(self, user_id: UUID, workspace_id: UUID) -> None: ...

    def update(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        status: WorkspaceOperationalStatus,
        ai_execution_enabled: bool,
    ) -> WorkspaceOperationalState: ...
