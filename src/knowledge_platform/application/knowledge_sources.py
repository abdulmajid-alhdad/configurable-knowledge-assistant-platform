"""Knowledge source registration use cases."""
# ruff: noqa: E501

from typing import Protocol

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class KnowledgeSourceRepositoryPort(Protocol):
    def add(self, source: KnowledgeSource, *, workspace_id: WorkspaceId) -> None: ...
    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[KnowledgeSource]: ...
    def get(self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId) -> KnowledgeSource | None: ...


class KnowledgeSourceService:
    def __init__(self, repository: KnowledgeSourceRepositoryPort) -> None:
        self._repository = repository

    def register(self, *, workspace_id: WorkspaceId, name: str, kind: KnowledgeSourceKind) -> KnowledgeSource:
        source = KnowledgeSource.create(workspace_id=workspace_id, name=name, kind=kind)
        self._repository.add(source, workspace_id=workspace_id)
        return source

    def list(self, workspace_id: WorkspaceId) -> list[KnowledgeSource]:
        return self._repository.list_for_workspace(workspace_id)

    def get(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> KnowledgeSource | None:
        return self._repository.get(source_id=source_id, workspace_id=workspace_id)
