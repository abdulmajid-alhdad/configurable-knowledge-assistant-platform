"""Application foundation for SYSTEM-scoped administrative conversations."""

from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)


class SystemConversationRepositoryPort(Protocol):
    def add(self, conversation: SystemConversation) -> None: ...
    def get(self, conversation_id: UUID) -> SystemConversation | None: ...
    def list(
        self, *, status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE
    ) -> list[SystemConversation]: ...
    def rename(self, conversation_id: UUID, title: str) -> SystemConversation | None: ...
    def set_archived(
        self, conversation_id: UUID, archived: bool
    ) -> SystemConversation | None: ...


class SystemConversationControlPort(Protocol):
    """Transaction-owning boundary used by System delivery adapters."""

    def create(self, actor: UUID, *, title: str) -> SystemConversation: ...

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


class SystemConversationService:
    """Authorizes by SYSTEM scope; ``created_by`` never filters visibility."""

    def __init__(
        self,
        *,
        access: AccessControlPort,
        repository: SystemConversationRepositoryPort,
    ) -> None:
        self._access = access
        self._repository = repository

    def create(self, actor: UUID, *, title: str) -> SystemConversation:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_CREATE)
        value = SystemConversation.create(title=title, created_by=actor)
        self._repository.add(value)
        return value

    def get(self, actor: UUID, conversation_id: UUID) -> SystemConversation:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_READ)
        value = self._repository.get(conversation_id)
        if value is None:
            raise LookupError("system conversation not found")
        return value

    def list(
        self,
        actor: UUID,
        *,
        status: SystemConversationStatus | None = SystemConversationStatus.ACTIVE,
    ) -> list[SystemConversation]:
        self._access.require_system(actor, Permission.SYSTEM_CONVERSATIONS_READ)
        return self._repository.list(status=status)

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
