"""Explicit persistence adapters for Workspace and Assistant."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

from .mappers import (
    assistant_from_record,
    assistant_to_record,
    workspace_from_record,
    workspace_to_record,
)
from .models import AssistantRecord, WorkspaceRecord


class WorkspaceRepository:
    """Persistence adapter for explicit Workspace operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, workspace: Workspace) -> None:
        self._session.add(workspace_to_record(workspace))

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        record = self._session.get(WorkspaceRecord, workspace_id.value)
        return workspace_from_record(record) if record is not None else None


class AssistantRepository:
    """Persistence adapter for workspace-scoped Assistant operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, assistant: Assistant, *, workspace_id: WorkspaceId) -> None:
        if assistant.workspace_id != workspace_id:
            raise ValueError("assistant workspace does not match persistence workspace")
        self._session.add(assistant_to_record(assistant))

    def get(self, *, assistant_id: AssistantId, workspace_id: WorkspaceId) -> Assistant | None:
        statement = select(AssistantRecord).where(
            AssistantRecord.id == assistant_id.value,
            AssistantRecord.workspace_id == workspace_id.value,
        )
        record = self._session.scalar(statement)
        return assistant_from_record(record) if record is not None else None
