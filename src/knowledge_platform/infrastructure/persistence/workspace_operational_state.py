"""SQLAlchemy adapter for authoritative Workspace operational state."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.workspace_operational_state import (
    WorkspaceAIExecutionDisabled,
    WorkspaceOperationalState,
    WorkspaceSuspended,
)
from knowledge_platform.infrastructure.persistence.access_control import (
    AccessControlService,
)
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.workspace_assistant.domain.workspace import (
    WorkspaceOperationalStatus,
)


class WorkspaceOperationalStateService:
    """Reads state under the authenticated user's existing scoped RLS context."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
        self._access = AccessControlService(sessions)

    @contextmanager
    def _tx(self, user_id: UUID, workspace_id: UUID) -> Iterator[Session]:
        with self._sessions.begin() as session:
            session.execute(
                text("select set_config('app.user_id', :user, true)"),
                {"user": str(user_id)},
            )
            session.execute(
                text("select set_config('app.workspace_id', :workspace, true)"),
                {"workspace": str(workspace_id)},
            )
            yield session

    def get(self, user_id: UUID, workspace_id: UUID) -> WorkspaceOperationalState:
        with self._tx(user_id, workspace_id) as session:
            row = session.execute(
                text("""
                    select id,operational_status,ai_execution_enabled
                    from platform.workspaces where id=:workspace
                """),
                {"workspace": workspace_id},
            ).mappings().one_or_none()
        if row is None:
            raise LookupError("workspace not found")
        return WorkspaceOperationalState(
            workspace_id=workspace_id,
            status=WorkspaceOperationalStatus(str(row["operational_status"])),
            ai_execution_enabled=bool(row["ai_execution_enabled"]),
        )

    def require_active(self, user_id: UUID, workspace_id: UUID) -> None:
        state = self.get(user_id, workspace_id)
        if state.status is WorkspaceOperationalStatus.SUSPENDED:
            raise WorkspaceSuspended("WORKSPACE_SUSPENDED")

    def require_ai_execution(self, user_id: UUID, workspace_id: UUID) -> None:
        state = self.get(user_id, workspace_id)
        if state.status is WorkspaceOperationalStatus.SUSPENDED:
            raise WorkspaceSuspended("WORKSPACE_SUSPENDED")
        if not state.ai_execution_enabled:
            raise WorkspaceAIExecutionDisabled("WORKSPACE_AI_EXECUTION_DISABLED")

    def update(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        status: WorkspaceOperationalStatus,
        ai_execution_enabled: bool,
    ) -> WorkspaceOperationalState:
        """Apply an authoritative System-administered operational state."""
        self._access.require_system(actor, Permission.GOVERNANCE_MANAGE)
        with self._tx(actor, workspace_id) as session:
            changed = bool(
                session.execute(
                    text(
                        "select platform.update_workspace_operational_state"
                        "(:workspace,:status,:ai_enabled)"
                    ),
                    {
                        "workspace": workspace_id,
                        "status": status.value,
                        "ai_enabled": ai_execution_enabled,
                    },
                ).scalar_one()
            )
        if not changed:
            raise LookupError("workspace not found")
        return self.get(actor, workspace_id)
