"""Mappings between accepted Domain objects and persistence records."""

from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

from .models import AssistantRecord, WorkspaceRecord
from .payloads import ModelConfigurationPayload, RetrievalConfigurationPayload


def workspace_to_record(workspace: Workspace) -> WorkspaceRecord:
    return WorkspaceRecord(id=workspace.id.value, name=workspace.name)


def workspace_from_record(record: WorkspaceRecord) -> Workspace:
    return Workspace(id=WorkspaceId(record.id), name=record.name)


def assistant_to_record(assistant: Assistant) -> AssistantRecord:
    return AssistantRecord(
        id=assistant.id.value,
        workspace_id=assistant.workspace_id.value,
        name=assistant.name,
        description=assistant.description,
        instructions=assistant.instructions,
        language=assistant.language,
        model_configuration=ModelConfigurationPayload(
            provider=assistant.model_configuration.provider,
            model_reference=assistant.model_configuration.model_reference,
        ).model_dump(mode="json"),
        retrieval_configuration=RetrievalConfigurationPayload().model_dump(mode="json"),
    )


def assistant_from_record(record: AssistantRecord) -> Assistant:
    return Assistant(
        id=AssistantId(record.id),
        workspace_id=WorkspaceId(record.workspace_id),
        name=record.name,
        description=record.description,
        instructions=record.instructions,
        language=record.language,
        model_configuration=ModelConfiguration(
            **ModelConfigurationPayload.model_validate(record.model_configuration).model_dump()
        ),
        retrieval_configuration=RetrievalConfiguration(
            **RetrievalConfigurationPayload.model_validate(record.retrieval_configuration).model_dump()
        ),
    )
