"""Transaction-owning persistence boundary for System Conversations."""

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.application.system_conversations import SystemConversationService
from knowledge_platform.infrastructure.persistence.repositories import (
    SystemConversationRepository,
)
from knowledge_platform.infrastructure.persistence.workspace_context import (
    system_session_scope,
)
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)


class SqlAlchemySystemConversationControl:
    """Keep SYSTEM RLS context and persistence in one transaction per operation."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        access: AccessControlPort,
    ) -> None:
        self._sessions = sessions
        self._access = access

    def _service(self, session: Session) -> SystemConversationService:
        return SystemConversationService(
            access=self._access,
            repository=SystemConversationRepository(session),
        )

    def create(self, actor: UUID, *, title: str) -> SystemConversation:
        with system_session_scope(self._sessions) as session:
            return self._service(session).create(actor, title=title)

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
                actor, conversation_id, archived=archived
            )
