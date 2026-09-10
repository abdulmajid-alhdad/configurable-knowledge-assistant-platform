"""Transaction-owning persistence boundary for grounded System conversations."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.application.system_conversations import SystemConversationService
from knowledge_platform.application.workspace_operational_state import (
    WorkspaceOperationalStatePort,
)
from knowledge_platform.infrastructure.persistence.repositories import (
    AssistantKnowledgeSourceRepository,
    AssistantRepository,
    KnowledgeSourceRepository,
    SystemConversationRepository,
    WorkspaceRepository,
)
from knowledge_platform.infrastructure.persistence.workspace_context import (
    system_session_scope,
    workspace_session_scope,
)
from knowledge_platform.modules.evidence_grounding.domain.contracts import GroundingOutcome
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


class SqlAlchemySystemConversationControl:
    """Keeps System authority and selected-Workspace RLS context separate."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        access: AccessControlPort,
        workspace_state: WorkspaceOperationalStatePort,
        rag_factory: Callable[[Session], DocumentRagService],
    ) -> None:
        self._sessions = sessions
        self._access = access
        self._workspace_state = workspace_state
        self._rag_factory = rag_factory

    def _service(self, session: Session) -> SystemConversationService:
        return SystemConversationService(
            access=self._access,
            repository=SystemConversationRepository(session),
            workspaces=WorkspaceRepository(session),
            assistants=AssistantRepository(session),
            sources=KnowledgeSourceRepository(session),
            associations=AssistantKnowledgeSourceRepository(session),
        )

    def _execution_service(self, session: Session) -> SystemConversationService:
        return SystemConversationService(
            access=self._access,
            repository=SystemConversationRepository(session),
            workspaces=WorkspaceRepository(session),
            assistants=AssistantRepository(session),
            sources=KnowledgeSourceRepository(session),
            associations=AssistantKnowledgeSourceRepository(session),
            rag=self._rag_factory(session),
        )

    def create(
        self,
        actor: UUID,
        *,
        workspace_id: UUID,
        assistant_id: UUID,
        title: str,
    ) -> SystemConversation:
        with system_session_scope(self._sessions) as session:
            return self._service(session).create(
                actor,
                workspace_id=WorkspaceId(workspace_id),
                assistant_id=AssistantId(assistant_id),
                title=title,
            )

    def get(self, actor: UUID, conversation_id: UUID) -> SystemConversation:
        with system_session_scope(self._sessions) as session:
            return self._service(session).get(actor, conversation_id)

    def list(
        self,
        actor: UUID,
        *,
        status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE,
    ) -> list[SystemConversation]:
        with system_session_scope(self._sessions) as session:
            return self._service(session).list(actor, status=status)

    def rename(
        self, actor: UUID, conversation_id: UUID, *, title: str
    ) -> SystemConversation:
        with system_session_scope(self._sessions) as session:
            return self._service(session).rename(actor, conversation_id, title=title)

    def set_archived(
        self, actor: UUID, conversation_id: UUID, *, archived: bool
    ) -> SystemConversation:
        with system_session_scope(self._sessions) as session:
            return self._service(session).set_archived(
                actor,
                conversation_id,
                archived=archived,
            )

    def ask(
        self, actor: UUID, conversation_id: UUID, *, question: str
    ) -> GroundingOutcome:
        with system_session_scope(self._sessions) as session:
            workspace_id = self._service(session).execution_workspace(
                actor,
                conversation_id,
            )
        self._workspace_state.require_ai_execution(actor, workspace_id.value)
        with workspace_session_scope(self._sessions, workspace_id) as session:
            outcome = self._execution_service(session).ask(
                actor,
                conversation_id,
                question=question,
            )
            session.execute(
                text("""
                    select platform.record_usage_event(
                      :workspace,'assistant.question',1,'operations',
                      'system_conversation',:conversation,'{}'::jsonb)
                """),
                {"workspace": workspace_id.value, "conversation": conversation_id},
            )
            return outcome
