"""Explicit persistence adapters for Workspace and Assistant."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

from .mappers import (
    assistant_from_record,
    assistant_to_record,
    knowledge_source_from_record,
    knowledge_source_to_record,
    workspace_from_record,
    workspace_to_record,
)
from .models import AssistantRecord, KnowledgeSourceRecord, WorkspaceRecord


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


class KnowledgeSourceRepository:
    """Explicit workspace-scoped persistence for KnowledgeSource aggregates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, source: KnowledgeSource, *, workspace_id: WorkspaceId) -> None:
        if source.workspace_id != workspace_id:
            raise ValueError("knowledge source workspace does not match persistence workspace")
        self._session.add(knowledge_source_to_record(source))

    def get(
        self,
        *,
        source_id: KnowledgeSourceId,
        workspace_id: WorkspaceId,
    ) -> KnowledgeSource | None:
        statement = select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.id == source_id.value,
            KnowledgeSourceRecord.workspace_id == workspace_id.value,
        )
        record = self._session.scalar(statement)
        return knowledge_source_from_record(record) if record is not None else None

    def save_transition(
        self,
        *,
        previous: KnowledgeSource,
        transitioned: KnowledgeSource,
        workspace_id: WorkspaceId,
    ) -> None:
        if previous.workspace_id != workspace_id or transitioned.workspace_id != workspace_id:
            raise ValueError("knowledge source workspace does not match persistence workspace")
        if previous.id != transitioned.id:
            raise ValueError("knowledge source identity does not match transition")
        if (previous.name, previous.kind) != (transitioned.name, transitioned.kind):
            raise ValueError("lifecycle transition cannot change name or kind")
        previous.validate_successor(transitioned)
        result = self._session.execute(
            update(KnowledgeSourceRecord)
            .where(
                KnowledgeSourceRecord.id == previous.id.value,
                KnowledgeSourceRecord.workspace_id == workspace_id.value,
                KnowledgeSourceRecord.lifecycle == previous.lifecycle.value,
            )
            .values(lifecycle=transitioned.lifecycle.value)
        )
        if getattr(result, "rowcount", 0) == 0:
            raise RuntimeError("knowledge source transition conflict or source not found")
