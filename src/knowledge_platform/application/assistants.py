"""Assistant management use cases."""
# ruff: noqa: E501

from typing import Protocol

from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


class AssistantRepositoryPort(Protocol):
    def add(self, assistant: Assistant, *, workspace_id: WorkspaceId) -> None: ...
    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[Assistant]: ...
    def get(self, *, assistant_id: AssistantId, workspace_id: WorkspaceId) -> Assistant | None: ...
    def save_reconfiguration(self, *, previous: Assistant, reconfigured: Assistant,
                             workspace_id: WorkspaceId) -> None: ...


class AssistantService:
    def __init__(self, repository: AssistantRepositoryPort) -> None:
        self._repository = repository

    def create(self, *, workspace_id: WorkspaceId, name: str, description: str | None,
               instructions: str, language: str, provider: str, model_reference: str) -> Assistant:
        assistant = Assistant.create(
            workspace_id=workspace_id, name=name, description=description,
            instructions=instructions, language=language,
            model_configuration=ModelConfiguration(provider=provider, model_reference=model_reference),
            retrieval_configuration=RetrievalConfiguration(),
        )
        self._repository.add(assistant, workspace_id=workspace_id)
        return assistant

    def list(self, workspace_id: WorkspaceId) -> list[Assistant]:
        return self._repository.list_for_workspace(workspace_id)

    def get(self, *, workspace_id: WorkspaceId, assistant_id: AssistantId) -> Assistant | None:
        return self._repository.get(assistant_id=assistant_id, workspace_id=workspace_id)

    def reconfigure(self, *, workspace_id: WorkspaceId, assistant_id: AssistantId,
                    name: str, description: str | None, instructions: str,
                    language: str, provider: str, model_reference: str) -> Assistant:
        previous = self.get(workspace_id=workspace_id, assistant_id=assistant_id)
        if previous is None:
            raise LookupError("assistant not found")
        updated = previous.reconfigure(
            name=name, description=description, instructions=instructions,
            language=language,
            model_configuration=ModelConfiguration(provider=provider, model_reference=model_reference),
            retrieval_configuration=RetrievalConfiguration(),
        )
        self._repository.save_reconfiguration(
            previous=previous, reconfigured=updated, workspace_id=workspace_id
        )
        return updated
