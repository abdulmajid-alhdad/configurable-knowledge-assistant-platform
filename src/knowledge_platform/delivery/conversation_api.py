"""Persisted conversation and assistant ask endpoints."""
import logging
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.workspace_operational_state import (
    WorkspaceOperationalError,
)
from knowledge_platform.modules.conversation.domain.conversation import (
    Conversation,
    ConversationStatus,
)
from knowledge_platform.modules.conversation.domain.message import MessageOutcome
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    InsufficientEvidence,
    PolicyDenied,
    TechnicalFailure,
)

logger = logging.getLogger(__name__)

_PUBLIC_OUTCOMES = {
    MessageOutcome.GROUNDED: "GroundedAnswer",
    MessageOutcome.INSUFFICIENT_EVIDENCE: "InsufficientEvidence",
    MessageOutcome.POLICY_DENIED: "PolicyDenied",
    MessageOutcome.TECHNICAL_FAILURE: "TechnicalFailure",
}


def _public_outcome(value: MessageOutcome | None) -> str | None:
    return _PUBLIC_OUTCOMES[value] if value is not None else None


def _database_diagnostics(error: Exception) -> dict[str, str]:
    diagnostics: dict[str, str] = {}
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        diag = getattr(current, "diag", None)
        if diag is None:
            original = getattr(current, "orig", None)
            diag = getattr(original, "diag", None)
        if diag is not None:
            for field, key in (
                ("sqlstate", "sqlstate"),
                ("constraint_name", "constraint_name"),
                ("table_name", "table_name"),
                ("schema_name", "schema_name"),
            ):
                value = getattr(diag, field, None)
                if isinstance(value, str) and value:
                    diagnostics.setdefault(key, value)
        current = current.__cause__ or current.__context__
    return diagnostics


def _log_ask_failure(*, workspace_id: UUID, conversation_id: UUID, error: Exception) -> None:
    """Log ask failure location without serializing private request details."""
    context = {
        "workspace_id": str(workspace_id),
        "conversation_id": str(conversation_id),
        "exception_type": type(error).__name__,
    }
    diagnostics = _database_diagnostics(error)
    context.update(diagnostics)
    rendered_diagnostics = " ".join(
        f"{field}={diagnostics.get(field, 'unknown')}"
        for field in ("sqlstate", "constraint_name", "table_name", "schema_name")
    )
    logger.error(
        "conversation_ask_failed workspace_id=%s conversation_id=%s "
        "exception_type=%s %s",
        workspace_id,
        conversation_id,
        type(error).__name__,
        rendered_diagnostics,
        extra=context,
    )


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)


class ConversationRenameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class ConversationArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool


class ConversationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    assistant_id: UUID
    title: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None
    archived_at: datetime | None
    messages: list[dict[str, object]]


class ConversationSummaryResponse(BaseModel):
    id: UUID
    assistant_id: UUID
    title: str
    status: str
    created_at: datetime | None
    message_count: int
    last_message_preview: str | None
    last_outcome: str | None


class ConversationServices(Protocol):
    def create_conversation(self, workspace_id: UUID, assistant_id: UUID) -> Conversation: ...
    def get_conversation(
        self, workspace_id: UUID, conversation_id: UUID
    ) -> Conversation | None: ...
    def list_conversations(
        self,
        workspace_id: UUID,
        assistant_id: UUID | None = None,
        conversation_status: ConversationStatus | None = ConversationStatus.ACTIVE,
    ) -> list[Conversation]: ...
    def rename_conversation(
        self, workspace_id: UUID, conversation_id: UUID, title: str
    ) -> Conversation: ...
    def set_conversation_archived(
        self, workspace_id: UUID, conversation_id: UUID, archived: bool
    ) -> Conversation: ...
    def ask_conversation(
        self, workspace_id: UUID, conversation_id: UUID, question: str
    ) -> object: ...


def _conversation(value: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=value.id.value,
        workspace_id=value.workspace_id.value,
        assistant_id=value.assistant_id.value,
        title=value.title,
        status=value.status.value,
        created_at=value.created_at,
        updated_at=value.updated_at,
        archived_at=value.archived_at,
        messages=[
            {
                "sequence": m.sequence,
                "role": m.role.value,
                "content": m.content,
                "outcome": _public_outcome(m.outcome),
                "evidence": [
                    {
                        "source_id": str(item.source_id.value),
                        "content": item.content,
                        "provenance_locator": item.provenance_locator,
                    }
                    for item in m.evidence
                ],
            }
            for m in value.messages
        ],
    )


def _outcome(value: object) -> dict[str, object]:
    if isinstance(value, GroundedAnswer):
        return {
            "outcome": "GroundedAnswer", "answer": value.answer, "evidence": [
                {
                    "source_id": str(item.source_id.value), "content": item.content,
                    "provenance_locator": item.provenance_locator,
                }
                for item in value.evidence
            ]
        }
    if isinstance(value, InsufficientEvidence):
        return {"outcome": "InsufficientEvidence", "reason": value.reason}
    if isinstance(value, PolicyDenied):
        return {"outcome": "PolicyDenied", "reason": value.reason}
    if isinstance(value, TechnicalFailure):
        return {"outcome": "TechnicalFailure", "reason": "request could not be completed"}
    return {"outcome": "TechnicalFailure", "reason": "request could not be completed"}


def create_conversation_router(services: ConversationServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post(
        "/workspaces/{workspace_id}/assistants/{assistant_id}/conversations",
        response_model=ConversationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create(workspace_id: UUID, assistant_id: UUID) -> ConversationResponse:
        try:
            return _conversation(services.create_conversation(workspace_id, assistant_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant not found") from exc

    @router.get(
        "/workspaces/{workspace_id}/conversations",
        response_model=list[ConversationSummaryResponse],
    )
    def list_conversations(
        workspace_id: UUID,
        assistant_id: UUID | None = None,
        conversation_status: ConversationStatus | None = ConversationStatus.ACTIVE,
    ) -> list[ConversationSummaryResponse]:
        try:
            return [
                ConversationSummaryResponse(
                    id=value.id.value,
                    assistant_id=value.assistant_id.value,
                    title=value.title,
                    status=value.status.value,
                    created_at=value.created_at,
                    message_count=len(value.messages),
                    last_message_preview=(
                        value.messages[-1].content[:120] if value.messages else None
                    ),
                    last_outcome=(
                        _public_outcome(value.messages[-1].outcome)
                        if value.messages else None
                    ),
                )
                for value in services.list_conversations(
                    workspace_id, assistant_id, conversation_status
                )
            ]
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant not found") from exc

    @router.get(
        "/workspaces/{workspace_id}/conversations/{conversation_id}",
        response_model=ConversationResponse,
    )
    def get(workspace_id: UUID, conversation_id: UUID) -> ConversationResponse:
        value = services.get_conversation(workspace_id, conversation_id)
        if value is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return _conversation(value)

    @router.patch(
        "/workspaces/{workspace_id}/conversations/{conversation_id}/title",
        response_model=ConversationResponse,
    )
    def rename(
        workspace_id: UUID,
        conversation_id: UUID,
        payload: ConversationRenameInput,
    ) -> ConversationResponse:
        try:
            return _conversation(
                services.rename_conversation(
                    workspace_id, conversation_id, payload.title
                )
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc

    @router.patch(
        "/workspaces/{workspace_id}/conversations/{conversation_id}/archive",
        response_model=ConversationResponse,
    )
    def set_archived(
        workspace_id: UUID,
        conversation_id: UUID,
        payload: ConversationArchiveInput,
    ) -> ConversationResponse:
        try:
            return _conversation(
                services.set_conversation_archived(
                    workspace_id, conversation_id, payload.archived
                )
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc

    @router.post("/workspaces/{workspace_id}/conversations/{conversation_id}/ask")
    def ask(
        workspace_id: UUID, conversation_id: UUID, payload: QuestionInput
    ) -> dict[str, object]:
        try:
            return _outcome(
                services.ask_conversation(workspace_id, conversation_id, payload.question)
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc
        except WorkspaceOperationalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            _log_ask_failure(
                workspace_id=workspace_id, conversation_id=conversation_id, error=exc
            )
            raise HTTPException(status_code=500, detail="request could not be completed") from exc

    return router
