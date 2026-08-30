"""Application service for explicit assistant/source authorization."""
# ruff: noqa: E501

from typing import Protocol

from knowledge_platform.modules.knowledge_sources.domain.access import KnowledgeAccessScope
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


class AssistantRepositoryPort(Protocol):
    def get(self, *, assistant_id: AssistantId, workspace_id: WorkspaceId) -> Assistant | None: ...


class SourceRepositoryPort(Protocol):
    def get(self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId) -> KnowledgeSource | None: ...


class AssociationRepositoryPort(Protocol):
    def attach(self, *, assistant_id: AssistantId, source_id: KnowledgeSourceId,
               workspace_id: WorkspaceId) -> None: ...
    def detach(self, *, assistant_id: AssistantId, source_id: KnowledgeSourceId,
               workspace_id: WorkspaceId) -> None: ...
    def list_source_ids(self, *, assistant_id: AssistantId,
                        workspace_id: WorkspaceId) -> frozenset[KnowledgeSourceId]: ...


class AssistantKnowledgeScopeService:
    def __init__(self, *, assistants: AssistantRepositoryPort,
                 sources: SourceRepositoryPort,
                 associations: AssociationRepositoryPort) -> None:
        self._assistants = assistants
        self._sources = sources
        self._associations = associations

    def attach(self, *, workspace_id: WorkspaceId, assistant_id: AssistantId,
               source_id: KnowledgeSourceId) -> None:
        assistant = self._assistants.get(assistant_id=assistant_id, workspace_id=workspace_id)
        source = self._sources.get(source_id=source_id, workspace_id=workspace_id)
        if assistant is None or source is None:
            raise LookupError("assistant or source not found")
        self._associations.attach(
            assistant_id=assistant_id, source_id=source_id, workspace_id=workspace_id
        )

    def detach(self, *, workspace_id: WorkspaceId, assistant_id: AssistantId,
               source_id: KnowledgeSourceId) -> None:
        self._associations.detach(
            assistant_id=assistant_id, source_id=source_id, workspace_id=workspace_id
        )

    def source_ids(self, *, workspace_id: WorkspaceId,
                   assistant_id: AssistantId) -> frozenset[KnowledgeSourceId]:
        return self._associations.list_source_ids(
            assistant_id=assistant_id, workspace_id=workspace_id
        )

    def scope(self, *, workspace_id: WorkspaceId, assistant: Assistant,
              sources: list[KnowledgeSource]) -> KnowledgeAccessScope:
        return KnowledgeAccessScope.for_assistant(assistant=assistant, sources=sources)
