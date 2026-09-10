"""Grounded SYSTEM conversations over a selected Workspace Assistant."""

from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.conversation.domain.message import (
    MessageEvidence,
    MessageOutcome,
)
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    GroundingOutcome,
    InsufficientEvidence,
    PolicyDenied,
    TechnicalFailure,
)
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


class SystemConversationConflict(ValueError):
    """Stable conflict for archived or legacy System conversation execution."""


class SystemConversationRepositoryPort(Protocol):
    def add(self, conversation: SystemConversation) -> None: ...
    def get(self, conversation_id: UUID) -> SystemConversation | None: ...
    def get_for_update(self, conversation_id: UUID) -> SystemConversation | None: ...
    def list(
        self, *, status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE
    ) -> list[SystemConversation]: ...
    def rename(self, conversation_id: UUID, title: str) -> SystemConversation | None: ...
    def set_archived(
        self, conversation_id: UUID, archived: bool
    ) -> SystemConversation | None: ...
    def add_message(self, conversation: SystemConversation) -> None: ...


class SystemAssistantRepositoryPort(Protocol):
    def get(
        self, *, assistant_id: AssistantId, workspace_id: WorkspaceId
    ) -> Assistant | None: ...


class SystemSourceRepositoryPort(Protocol):
    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[KnowledgeSource]: ...


class SystemAssociationRepositoryPort(Protocol):
    def list_source_ids(
        self, *, assistant_id: AssistantId, workspace_id: WorkspaceId
    ) -> frozenset[KnowledgeSourceId]: ...


class SystemWorkspaceRepositoryPort(Protocol):
    def get(self, workspace_id: WorkspaceId) -> Workspace | None: ...


class SystemConversationControlPort(Protocol):
    """Transaction-owning boundary used only by System delivery adapters."""

    def create(
        self,
        actor: UUID,
        *,
        workspace_id: UUID,
        assistant_id: UUID,
        title: str,
    ) -> SystemConversation: ...

    def get(self, actor: UUID, conversation_id: UUID) -> SystemConversation: ...

    def list(
        self,
        actor: UUID,
        *,
        status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE,
    ) -> list[SystemConversation]: ...

    def rename(
        self, actor: UUID, conversation_id: UUID, *, title: str
    ) -> SystemConversation: ...

    def set_archived(
        self, actor: UUID, conversation_id: UUID, *, archived: bool
    ) -> SystemConversation: ...

    def ask(
        self, actor: UUID, conversation_id: UUID, *, question: str
    ) -> GroundingOutcome: ...


def _answer_message(outcome: GroundingOutcome) -> tuple[
    str, MessageOutcome, tuple[MessageEvidence, ...]
]:
    if isinstance(outcome, GroundedAnswer):
        return (
            outcome.answer,
            MessageOutcome.GROUNDED,
            tuple(
                MessageEvidence(
                    source_id=item.source_id,
                    content=item.content,
                    provenance_locator=item.provenance_locator,
                )
                for item in outcome.evidence
            ),
        )
    if isinstance(outcome, InsufficientEvidence):
        return outcome.reason, MessageOutcome.INSUFFICIENT_EVIDENCE, ()
    if isinstance(outcome, PolicyDenied):
        return outcome.reason, MessageOutcome.POLICY_DENIED, ()
    if isinstance(outcome, TechnicalFailure):
        return outcome.reason, MessageOutcome.TECHNICAL_FAILURE, ()
    raise TypeError("unsupported grounding outcome")


class SystemConversationService:
    """SYSTEM-authorized, Assistant-bound conversation orchestration."""

    def __init__(
        self,
        *,
        access: AccessControlPort,
        repository: SystemConversationRepositoryPort,
        workspaces: SystemWorkspaceRepositoryPort,
        assistants: SystemAssistantRepositoryPort,
        sources: SystemSourceRepositoryPort,
        associations: SystemAssociationRepositoryPort,
        rag: DocumentRagService | None = None,
    ) -> None:
        self._access = access
        self._repository = repository
        self._workspaces = workspaces
        self._assistants = assistants
        self._sources = sources
        self._associations = associations
        self._rag = rag

    def _require_execution_visibility(self, actor: UUID) -> None:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_READ)
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_CREATE)
        self._access.require_system(actor, Permission.SYSTEM_WORKSPACES_READ)
        self._access.require_system(actor, Permission.SYSTEM_ASSISTANTS_READ)
        self._access.require_system(actor, Permission.SYSTEM_KNOWLEDGE_READ)

    def _require_bound_visibility(
        self, actor: UUID, conversation: SystemConversation
    ) -> None:
        if not conversation.is_bound:
            return
        self._access.require_system(actor, Permission.SYSTEM_WORKSPACES_READ)
        self._access.require_system(actor, Permission.SYSTEM_ASSISTANTS_READ)
        self._access.require_system(actor, Permission.SYSTEM_KNOWLEDGE_READ)

    def create(
        self,
        actor: UUID,
        *,
        workspace_id: WorkspaceId,
        assistant_id: AssistantId,
        title: str,
    ) -> SystemConversation:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_CREATE)
        self._access.require_system(actor, Permission.SYSTEM_WORKSPACES_READ)
        self._access.require_system(actor, Permission.SYSTEM_ASSISTANTS_READ)
        if self._workspaces.get(workspace_id) is None:
            raise LookupError("workspace not found")
        if self._assistants.get(
            assistant_id=assistant_id, workspace_id=workspace_id
        ) is None:
            raise LookupError("assistant not found")
        value = SystemConversation.create(
            title=title,
            created_by=actor,
            workspace_id=workspace_id,
            assistant_id=assistant_id,
        )
        self._repository.add(value)
        return value

    def get(self, actor: UUID, conversation_id: UUID) -> SystemConversation:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_READ)
        value = self._repository.get(conversation_id)
        if value is None:
            raise LookupError("system conversation not found")
        self._require_bound_visibility(actor, value)
        return value

    def list(
        self,
        actor: UUID,
        *,
        status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE,
    ) -> list[SystemConversation]:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_READ)
        values = self._repository.list(status=status)
        for value in values:
            self._require_bound_visibility(actor, value)
        return values

    def rename(
        self, actor: UUID, conversation_id: UUID, *, title: str
    ) -> SystemConversation:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_RENAME)
        value = self._repository.rename(conversation_id, title)
        if value is None:
            raise LookupError("system conversation not found")
        return value

    def set_archived(
        self, actor: UUID, conversation_id: UUID, *, archived: bool
    ) -> SystemConversation:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_ARCHIVE)
        value = self._repository.set_archived(conversation_id, archived)
        if value is None:
            raise LookupError("system conversation not found")
        return value

    def execution_workspace(self, actor: UUID, conversation_id: UUID) -> WorkspaceId:
        self._require_execution_visibility(actor)
        conversation = self._repository.get(conversation_id)
        if conversation is None:
            raise LookupError("system conversation not found")
        if conversation.status is SystemConversationStatus.ARCHIVED:
            raise SystemConversationConflict("system conversation is archived")
        if not conversation.is_bound:
            raise SystemConversationConflict("system conversation is legacy and unbound")
        assert conversation.workspace_id is not None
        return conversation.workspace_id

    def ask(
        self, actor: UUID, conversation_id: UUID, *, question: str
    ) -> GroundingOutcome:
        self._require_execution_visibility(actor)
        rag = self._rag
        if rag is None:
            raise RuntimeError("RAG execution dependency is required for system conversation ask")
        conversation = self._repository.get_for_update(conversation_id)
        if conversation is None:
            raise LookupError("system conversation not found")
        if conversation.status is SystemConversationStatus.ARCHIVED:
            raise SystemConversationConflict("system conversation is archived")
        if not conversation.is_bound:
            raise SystemConversationConflict("system conversation is legacy and unbound")
        assert conversation.workspace_id is not None
        assert conversation.assistant_id is not None
        if self._workspaces.get(conversation.workspace_id) is None:
            raise LookupError("workspace not found")
        assistant = self._assistants.get(
            assistant_id=conversation.assistant_id,
            workspace_id=conversation.workspace_id,
        )
        if assistant is None:
            raise LookupError("assistant not found")
        authorized = self._associations.list_source_ids(
            assistant_id=assistant.id,
            workspace_id=conversation.workspace_id,
        )
        eligible = frozenset(
            source.id
            for source in self._sources.list_for_workspace(conversation.workspace_id)
            if source.id in authorized and source.is_retrieval_eligible
        )
        with_question = conversation.append_message(
            role=MessageRole.USER,
            content=question,
        )
        self._repository.add_message(with_question)
        outcome = rag.ask(
            workspace_id=conversation.workspace_id,
            assistant_id=assistant.id,
            question=question,
            source_ids=eligible,
            assistant_instructions=assistant.instructions,
        )
        answer, persisted_outcome, evidence = _answer_message(outcome)
        self._repository.add_message(
            with_question.append_message(
                role=MessageRole.ASSISTANT,
                content=answer,
                outcome=persisted_outcome,
                evidence=evidence,
            )
        )
        return outcome
