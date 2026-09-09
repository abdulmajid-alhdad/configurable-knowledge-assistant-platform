"""Mappings between accepted Domain objects and persistence records."""

from uuid import UUID

from knowledge_platform.modules.conversation.domain.conversation import (
    Conversation,
    ConversationStatus,
)
from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.conversation.domain.message import (
    Message,
    MessageEvidence,
    MessageOutcome,
)
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
    KnowledgeSourceLifecycle,
)
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
    SystemMessage,
)
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import (
    Workspace,
    WorkspaceOperationalStatus,
)

from .models import (
    AssistantRecord,
    ConversationRecord,
    KnowledgeSourceRecord,
    MessageEvidenceRecord,
    MessageRecord,
    SystemConversationMessageRecord,
    SystemConversationRecord,
    WorkspaceRecord,
)
from .payloads import ModelConfigurationPayload, RetrievalConfigurationPayload


def workspace_to_record(workspace: Workspace) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=workspace.id.value,
        name=workspace.name,
        operational_status=workspace.operational_status.value,
        ai_execution_enabled=workspace.ai_execution_enabled,
    )


def workspace_from_record(record: WorkspaceRecord) -> Workspace:
    return Workspace(
        id=WorkspaceId(record.id),
        name=record.name,
        operational_status=WorkspaceOperationalStatus(record.operational_status),
        ai_execution_enabled=record.ai_execution_enabled,
    )


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


def knowledge_source_to_record(source: KnowledgeSource) -> KnowledgeSourceRecord:
    return KnowledgeSourceRecord(
        id=source.id.value,
        workspace_id=source.workspace_id.value,
        name=source.name,
        kind=source.kind.value,
        lifecycle=source.lifecycle.value,
    )


def knowledge_source_from_record(record: KnowledgeSourceRecord) -> KnowledgeSource:
    return KnowledgeSource(
        id=KnowledgeSourceId(record.id),
        workspace_id=WorkspaceId(record.workspace_id),
        name=record.name,
        kind=KnowledgeSourceKind(record.kind),
        lifecycle=KnowledgeSourceLifecycle(record.lifecycle),
    )


def conversation_to_record(conversation: Conversation) -> ConversationRecord:
    return ConversationRecord(
        id=conversation.id.value,
        workspace_id=conversation.workspace_id.value,
        assistant_id=conversation.assistant_id.value,
        title=conversation.title,
        status=conversation.status.value,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        archived_at=conversation.archived_at,
    )


def message_to_record(conversation_id: ConversationId, message: Message) -> MessageRecord:
    return MessageRecord(
        conversation_id=conversation_id.value,
        sequence=message.sequence,
        role=message.role.value,
        content=message.content,
        outcome=message.outcome.value if message.outcome is not None else None,
    )


def message_evidence_to_records(
    conversation_id: ConversationId, message: Message,
) -> list[MessageEvidenceRecord]:
    return [
        MessageEvidenceRecord(
            conversation_id=conversation_id.value,
            message_sequence=message.sequence,
            ordinal=ordinal,
            source_id=item.source_id.value,
            content=item.content,
            provenance_locator=item.provenance_locator,
        )
        for ordinal, item in enumerate(message.evidence, start=1)
    ]


def conversation_from_records(
    record: ConversationRecord, messages: list[MessageRecord],
    evidence: list[MessageEvidenceRecord] | None = None,
) -> Conversation:
    grouped: dict[int, list[MessageEvidenceRecord]] = {}
    for item in evidence or []:
        grouped.setdefault(item.message_sequence, []).append(item)
    return Conversation(
        id=ConversationId(record.id),
        workspace_id=WorkspaceId(record.workspace_id),
        assistant_id=AssistantId(record.assistant_id),
        messages=tuple(
            Message(
                sequence=item.sequence,
                role=MessageRole(item.role),
                content=item.content,
                outcome=MessageOutcome(item.outcome) if item.outcome is not None else None,
                evidence=tuple(
                    MessageEvidence(
                        source_id=KnowledgeSourceId(value.source_id),
                        content=value.content,
                        provenance_locator=value.provenance_locator,
                    )
                    for value in sorted(
                        grouped.get(item.sequence, []), key=lambda value: value.ordinal
                    )
                ),
            )
            for item in sorted(messages, key=lambda item: item.sequence)
        ),
        created_at=record.created_at,
        title=record.title,
        status=ConversationStatus(record.status),
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def system_conversation_to_record(
    conversation: SystemConversation,
) -> SystemConversationRecord:
    return SystemConversationRecord(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status.value,
        created_by=conversation.created_by,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        archived_at=conversation.archived_at,
    )


def system_message_to_record(
    conversation_id: UUID, message: SystemMessage
) -> SystemConversationMessageRecord:
    return SystemConversationMessageRecord(
        conversation_id=conversation_id,
        sequence=message.sequence,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
    )


def system_conversation_from_records(
    record: SystemConversationRecord,
    messages: list[SystemConversationMessageRecord],
) -> SystemConversation:
    return SystemConversation(
        id=record.id,
        title=record.title,
        status=SystemConversationStatus(record.status),
        created_by=record.created_by,
        messages=tuple(
            SystemMessage(
                sequence=message.sequence,
                role=MessageRole(message.role),
                content=message.content,
                created_at=message.created_at,
            )
            for message in sorted(messages, key=lambda value: value.sequence)
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )
