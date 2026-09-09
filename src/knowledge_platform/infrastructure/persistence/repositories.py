"""Explicit persistence adapters for Workspace and Assistant."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from knowledge_platform.modules.conversation.domain.conversation import (
    Conversation,
    ConversationStatus,
)
from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

from .mappers import (
    assistant_from_record,
    assistant_to_record,
    conversation_from_records,
    conversation_to_record,
    knowledge_source_from_record,
    knowledge_source_to_record,
    message_evidence_to_records,
    message_to_record,
    system_conversation_from_records,
    system_conversation_to_record,
    system_message_to_record,
    workspace_from_record,
    workspace_to_record,
)
from .models import (
    AssistantKnowledgeSourceRecord,
    AssistantRecord,
    ConversationRecord,
    KnowledgeSourceRecord,
    MessageEvidenceRecord,
    MessageRecord,
    SystemConversationMessageRecord,
    SystemConversationRecord,
    WorkspaceRecord,
)


class WorkspaceRepository:
    """Persistence adapter for explicit Workspace operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, workspace: Workspace) -> None:
        self._session.add(workspace_to_record(workspace))

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        record = self._session.get(WorkspaceRecord, workspace_id.value)
        if record is None:
            return None
        workspace = workspace_from_record(record)
        display_name = self._session.execute(
            text(
                "select display_name from platform.workspace_settings "
                "where workspace_id=:workspace"
            ),
            {"workspace": workspace_id.value},
        ).scalar_one_or_none()
        if isinstance(display_name, str) and display_name.strip():
            return replace(workspace, name=display_name)
        return workspace


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

    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[Assistant]:
        statement = select(AssistantRecord).where(
            AssistantRecord.workspace_id == workspace_id.value
        ).order_by(AssistantRecord.id)
        return [assistant_from_record(record) for record in self._session.scalars(statement)]

    def save_reconfiguration(
        self, *, previous: Assistant, reconfigured: Assistant,
        workspace_id: WorkspaceId,
    ) -> None:
        if previous.workspace_id != workspace_id or reconfigured.workspace_id != workspace_id:
            raise ValueError("assistant workspace does not match persistence workspace")
        if previous.id != reconfigured.id:
            raise ValueError("assistant identity does not match reconfiguration")
        changed = self._session.execute(
            text(
                "select platform.update_assistant_administration("
                ":workspace,:assistant,:name,:description,:instructions,"
                ":language,:provider,:model_reference)"
            ),
            {
                "workspace": workspace_id.value,
                "assistant": previous.id.value,
                "name": reconfigured.name,
                "description": reconfigured.description,
                "instructions": reconfigured.instructions,
                "language": reconfigured.language,
                "provider": reconfigured.model_configuration.provider,
                "model_reference": reconfigured.model_configuration.model_reference,
            },
        ).scalar_one()
        if changed is not True:
            raise RuntimeError("assistant not found")


class AssistantKnowledgeSourceRepository:
    """Explicit workspace-scoped assistant knowledge access persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def attach(self, *, assistant_id: AssistantId, source_id: KnowledgeSourceId,
               workspace_id: WorkspaceId) -> None:
        existing = self._session.scalar(
            select(AssistantKnowledgeSourceRecord).where(
                AssistantKnowledgeSourceRecord.workspace_id == workspace_id.value,
                AssistantKnowledgeSourceRecord.assistant_id == assistant_id.value,
                AssistantKnowledgeSourceRecord.knowledge_source_id == source_id.value,
            )
        )
        if existing is not None:
            return
        row = AssistantKnowledgeSourceRecord(
            workspace_id=workspace_id.value,
            assistant_id=assistant_id.value,
            knowledge_source_id=source_id.value,
        )
        self._session.add(row)

    def detach(self, *, assistant_id: AssistantId, source_id: KnowledgeSourceId,
               workspace_id: WorkspaceId) -> None:
        self._session.execute(
            delete(AssistantKnowledgeSourceRecord).where(
                AssistantKnowledgeSourceRecord.workspace_id == workspace_id.value,
                AssistantKnowledgeSourceRecord.assistant_id == assistant_id.value,
                AssistantKnowledgeSourceRecord.knowledge_source_id == source_id.value,
            )
        )

    def list_source_ids(self, *, assistant_id: AssistantId,
                        workspace_id: WorkspaceId) -> frozenset[KnowledgeSourceId]:
        statement = select(AssistantKnowledgeSourceRecord.knowledge_source_id).where(
            AssistantKnowledgeSourceRecord.workspace_id == workspace_id.value,
            AssistantKnowledgeSourceRecord.assistant_id == assistant_id.value,
        )
        return frozenset(KnowledgeSourceId(value) for value in self._session.scalars(statement))


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

    def get_for_update(
        self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId
    ) -> KnowledgeSource | None:
        statement = (
            select(KnowledgeSourceRecord)
            .where(
                KnowledgeSourceRecord.id == source_id.value,
                KnowledgeSourceRecord.workspace_id == workspace_id.value,
            )
            .with_for_update()
        )
        record = self._session.scalar(statement)
        return knowledge_source_from_record(record) if record is not None else None

    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[KnowledgeSource]:
        statement = select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.workspace_id == workspace_id.value
        ).order_by(KnowledgeSourceRecord.id)
        return [knowledge_source_from_record(record) for record in self._session.scalars(statement)]

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


class ConversationRepository:
    """Workspace-scoped persistence for conversations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conversation: Conversation, *, workspace_id: WorkspaceId) -> None:
        if conversation.workspace_id != workspace_id:
            raise ValueError("conversation workspace does not match persistence workspace")
        self._session.add(conversation_to_record(conversation))

    def get(
        self, *, conversation_id: ConversationId, workspace_id: WorkspaceId,
    ) -> Conversation | None:
        record = self._session.scalar(
            select(ConversationRecord).where(
                ConversationRecord.id == conversation_id.value,
                ConversationRecord.workspace_id == workspace_id.value,
            )
        )
        if record is None:
            return None
        messages = list(self._session.scalars(
            select(MessageRecord)
            .where(MessageRecord.conversation_id == conversation_id.value)
            .order_by(MessageRecord.sequence)
        ))
        evidence = list(self._session.scalars(
            select(MessageEvidenceRecord)
            .where(MessageEvidenceRecord.conversation_id == conversation_id.value)
            .order_by(
                MessageEvidenceRecord.message_sequence,
                MessageEvidenceRecord.ordinal,
            )
        ))
        return conversation_from_records(record, messages, evidence)

    def list_for_workspace(
        self, *, workspace_id: WorkspaceId,
        assistant_id: AssistantId | None = None,
        status: ConversationStatus | None = ConversationStatus.ACTIVE,
    ) -> list[Conversation]:
        statement = select(ConversationRecord).where(
            ConversationRecord.workspace_id == workspace_id.value
        )
        if assistant_id is not None:
            statement = statement.where(
                ConversationRecord.assistant_id == assistant_id.value
            )
        if status is not None:
            statement = statement.where(ConversationRecord.status == status.value)
        records = list(self._session.scalars(
            statement.order_by(
                ConversationRecord.created_at.desc().nulls_last(),
                ConversationRecord.id.desc(),
            )
        ))
        if not records:
            return []
        conversation_ids = [record.id for record in records]
        messages = list(self._session.scalars(
            select(MessageRecord)
            .where(MessageRecord.conversation_id.in_(conversation_ids))
            .order_by(MessageRecord.conversation_id, MessageRecord.sequence)
        ))
        evidence = list(self._session.scalars(
            select(MessageEvidenceRecord)
            .where(MessageEvidenceRecord.conversation_id.in_(conversation_ids))
            .order_by(
                MessageEvidenceRecord.conversation_id,
                MessageEvidenceRecord.message_sequence,
                MessageEvidenceRecord.ordinal,
            )
        ))
        messages_by_conversation: dict[object, list[MessageRecord]] = {}
        for message in messages:
            messages_by_conversation.setdefault(message.conversation_id, []).append(message)
        evidence_by_conversation: dict[object, list[MessageEvidenceRecord]] = {}
        for item in evidence:
            evidence_by_conversation.setdefault(item.conversation_id, []).append(item)
        return [
            conversation_from_records(
                record,
                messages_by_conversation.get(record.id, []),
                evidence_by_conversation.get(record.id, []),
            )
            for record in records
        ]

    def rename(
        self,
        *,
        conversation_id: ConversationId,
        workspace_id: WorkspaceId,
        title: str,
    ) -> Conversation | None:
        changed = self._session.execute(
            text(
                "select platform.rename_workspace_conversation"
                "(:workspace,:conversation,:title)"
            ),
            {
                "workspace": workspace_id.value,
                "conversation": conversation_id.value,
                "title": title,
            },
        ).scalar_one()
        if not changed:
            return None
        return self.get(conversation_id=conversation_id, workspace_id=workspace_id)

    def set_archived(
        self,
        *,
        conversation_id: ConversationId,
        workspace_id: WorkspaceId,
        archived: bool,
    ) -> Conversation | None:
        changed = self._session.execute(
            text(
                "select platform.set_workspace_conversation_archived"
                "(:workspace,:conversation,:archived)"
            ),
            {
                "workspace": workspace_id.value,
                "conversation": conversation_id.value,
                "archived": archived,
            },
        ).scalar_one()
        if not changed:
            return None
        return self.get(conversation_id=conversation_id, workspace_id=workspace_id)


class MessageRepository:
    """Append-only persistence for Conversation messages."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conversation: Conversation, *, workspace_id: WorkspaceId) -> None:
        if conversation.workspace_id != workspace_id:
            raise ValueError("conversation workspace does not match persistence workspace")
        if not conversation.messages:
            raise ValueError("conversation has no message to append")
        message = conversation.messages[-1]
        expected = len(conversation.messages) - 1
        if message.sequence != expected:
            raise ValueError("message sequence does not match append position")
        record = message_to_record(conversation.id, message)
        self._session.add(record)
        evidence = message_evidence_to_records(conversation.id, message)
        if evidence:
            # ORM mapper ordering alone does not establish a unit-of-work
            # dependency between these separately mapped records. Materialize
            # both pending messages before inserting their FK-backed evidence;
            # the outer workspace transaction still owns the only commit.
            self._session.flush()
            self._session.add_all(evidence)


class SystemConversationRepository:
    """Persistence adapter for the distinct SYSTEM-scope aggregate."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conversation: SystemConversation) -> None:
        self._session.add(system_conversation_to_record(conversation))

    def get(self, conversation_id: UUID) -> SystemConversation | None:
        record = self._session.get(SystemConversationRecord, conversation_id)
        if record is None:
            return None
        messages = list(
            self._session.scalars(
                select(SystemConversationMessageRecord)
                .where(
                    SystemConversationMessageRecord.conversation_id == conversation_id
                )
                .order_by(SystemConversationMessageRecord.sequence)
            )
        )
        return system_conversation_from_records(record, messages)

    def list(
        self, *, status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE
    ) -> list[SystemConversation]:
        statement = select(SystemConversationRecord)
        if status is not None:
            statement = statement.where(SystemConversationRecord.status == status.value)
        records = list(
            self._session.scalars(
                statement.order_by(
                    SystemConversationRecord.updated_at.desc(),
                    SystemConversationRecord.id.desc(),
                )
            )
        )
        return [
            value
            for record in records
            if (value := self.get(record.id)) is not None
        ]

    def rename(self, conversation_id: UUID, title: str) -> SystemConversation | None:
        changed = self._session.execute(
            text("select platform.rename_system_conversation(:conversation,:title)"),
            {"conversation": conversation_id, "title": title},
        ).scalar_one()
        return self.get(conversation_id) if changed else None

    def set_archived(
        self, conversation_id: UUID, archived: bool
    ) -> SystemConversation | None:
        changed = self._session.execute(
            text(
                "select platform.set_system_conversation_archived"
                "(:conversation,:archived)"
            ),
            {"conversation": conversation_id, "archived": archived},
        ).scalar_one()
        return self.get(conversation_id) if changed else None

    def add_message(self, conversation: SystemConversation) -> None:
        if not conversation.messages:
            raise ValueError("system conversation has no message to append")
        self._session.add(
            system_message_to_record(conversation.id, conversation.messages[-1])
        )
