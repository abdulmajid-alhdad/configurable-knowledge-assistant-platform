"""Application orchestration for persisted assistant conversations."""

from typing import Protocol

from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.evidence_grounding.domain.contracts import GroundingOutcome
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


class AssistantRepositoryPort(Protocol):
    def get(
        self, *, assistant_id: AssistantId, workspace_id: WorkspaceId
    ) -> Assistant | None: ...


class SourceRepositoryPort(Protocol):
    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[KnowledgeSource]: ...


class AssociationRepositoryPort(Protocol):
    def list_source_ids(
        self, *, assistant_id: AssistantId, workspace_id: WorkspaceId
    ) -> frozenset[KnowledgeSourceId]: ...


class ConversationRepositoryPort(Protocol):
    def add(self, conversation: Conversation, *, workspace_id: WorkspaceId) -> None: ...
    def get(
        self, *, conversation_id: ConversationId, workspace_id: WorkspaceId
    ) -> Conversation | None: ...


class MessageRepositoryPort(Protocol):
    def add(self, conversation: Conversation, *, workspace_id: WorkspaceId) -> None: ...


class AssistantConversationService:
    def __init__(
        self, *, assistants: AssistantRepositoryPort, sources: SourceRepositoryPort,
        associations: AssociationRepositoryPort, conversations: ConversationRepositoryPort,
        messages: MessageRepositoryPort, rag: DocumentRagService
    ) -> None:
        self._assistants, self._sources, self._associations = assistants, sources, associations
        self._conversations, self._messages, self._rag = conversations, messages, rag

    def create(self, *, workspace_id: WorkspaceId, assistant_id: AssistantId) -> Conversation:
        if self._assistants.get(assistant_id=assistant_id, workspace_id=workspace_id) is None:
            raise LookupError("assistant not found")
        conversation = Conversation.create_for_assistant(
            workspace_id=workspace_id, assistant_id=assistant_id
        )
        self._conversations.add(
            conversation, workspace_id=workspace_id
        )
        return conversation

    def get(self, *, workspace_id: WorkspaceId, conversation_id: ConversationId) -> Conversation | None:
        return self._conversations.get(conversation_id=conversation_id, workspace_id=workspace_id)

    def ask(self, *, workspace_id: WorkspaceId, conversation_id: ConversationId,
            question: str) -> GroundingOutcome:
        conversation = self.get(
            workspace_id=workspace_id, conversation_id=conversation_id
        )
        if conversation is None:
            raise LookupError("conversation not found")
        assistant = self._assistants.get(
            assistant_id=conversation.assistant_id, workspace_id=workspace_id
        )
        if assistant is None:
            raise LookupError("conversation not found")
        authorized = self._associations.list_source_ids(
            assistant_id=assistant.id, workspace_id=workspace_id
        )
        eligible = frozenset(
            source.id for source in self._sources.list_for_workspace(workspace_id)
            if source.id in authorized and source.is_retrieval_eligible
        )
        return self._rag.ask_in_conversation(
            conversation=conversation, workspace_id=workspace_id,
            assistant_id=assistant.id, question=question, source_ids=eligible,
            conversation_repository=self._conversations, message_repository=self._messages,
        )
