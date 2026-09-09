"""Evaluation execution adapter that delegates to normal assistant conversations."""

from typing import Protocol
from uuid import UUID

from knowledge_platform.application.evaluation import EvaluationExecutionPort
from knowledge_platform.modules.evaluation.domain.contracts import EvaluationCase


class ConversationIdentity(Protocol):
    @property
    def value(self) -> UUID: ...


class ConversationValue(Protocol):
    @property
    def id(self) -> ConversationIdentity: ...


class ConversationManagementPort(Protocol):
    def create_conversation(
        self, workspace_id: UUID, assistant_id: UUID
    ) -> ConversationValue: ...

    def ask_conversation(
        self, workspace_id: UUID, conversation_id: UUID, question: str
    ) -> object: ...


class AssistantEvaluationExecution(EvaluationExecutionPort):
    """Runs each case through persisted conversation and normal RAG boundaries."""

    def __init__(
        self,
        services: ConversationManagementPort,
        workspace_id: UUID,
        assistant_id: UUID,
    ) -> None:
        self._services = services
        self._workspace_id = workspace_id
        self._assistant_id = assistant_id
        self._conversation_id: UUID | None = None

    def execute(self, case: EvaluationCase) -> object:
        if self._conversation_id is None:
            conversation = self._services.create_conversation(
                self._workspace_id, self._assistant_id
            )
            self._conversation_id = conversation.id.value
        return self._services.ask_conversation(
            self._workspace_id, self._conversation_id, case.query
        )


class AssistantEvaluationExecutionFactory:
    def __init__(self, services: ConversationManagementPort) -> None:
        self._services = services

    def build(
        self, workspace_id: UUID, assistant_id: UUID
    ) -> AssistantEvaluationExecution:
        return AssistantEvaluationExecution(
            self._services, workspace_id, assistant_id
        )
