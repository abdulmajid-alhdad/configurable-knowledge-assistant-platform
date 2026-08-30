"""Workspace management use cases."""

from typing import Protocol

from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace


class WorkspaceRepositoryPort(Protocol):
    def add(self, workspace: Workspace) -> None: ...
    def get(self, workspace_id: WorkspaceId) -> Workspace | None: ...


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepositoryPort) -> None:
        self._repository = repository

    def create(self, *, name: str) -> Workspace:
        workspace = Workspace.create(name=name)
        self._repository.add(workspace)
        return workspace

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        return self._repository.get(workspace_id)
