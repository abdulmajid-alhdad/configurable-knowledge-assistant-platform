"""Delivery boundary for grounded, Assistant-bound System conversations."""

import logging
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowledge_platform.application.access_control import AccessDenied
from knowledge_platform.application.system_conversations import (
    SystemConversationConflict,
    SystemConversationControlPort,
)
from knowledge_platform.application.workspace_operational_state import (
    WorkspaceOperationalError,
)
from knowledge_platform.modules.conversation.domain.message import MessageOutcome
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    GroundingOutcome,
    InsufficientEvidence,
    PolicyDenied,
    TechnicalFailure,
)
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)

logger = logging.getLogger(__name__)

_PUBLIC_OUTCOMES = {
    MessageOutcome.GROUNDED: "GroundedAnswer",
    MessageOutcome.INSUFFICIENT_EVIDENCE: "InsufficientEvidence",
    MessageOutcome.POLICY_DENIED: "PolicyDenied",
    MessageOutcome.TECHNICAL_FAILURE: "TechnicalFailure",
}


class SystemConversationCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    assistant_id: UUID
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("system conversation title is blank")
        return normalized


class SystemConversationRenameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("system conversation title is blank")
        return normalized


class SystemConversationAskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("system conversation question is blank")
        return normalized


class SystemConversationArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool


def _public_outcome(value: MessageOutcome | None) -> str | None:
    return _PUBLIC_OUTCOMES[value] if value is not None else None


def _payload(value: SystemConversation) -> dict[str, object]:
    return {
        "id": value.id,
        "workspace_id": (
            value.workspace_id.value if value.workspace_id is not None else None
        ),
        "assistant_id": (
            value.assistant_id.value if value.assistant_id is not None else None
        ),
        "title": value.title,
        "status": value.status.value,
        "created_by": value.created_by,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "archived_at": value.archived_at,
        "messages": [
            {
                "sequence": message.sequence,
                "role": message.role.value,
                "content": message.content,
                "created_at": message.created_at,
                "outcome": _public_outcome(message.outcome),
                "evidence": [
                    {
                        "source_id": item.source_id.value,
                        "content": item.content,
                        "provenance_locator": item.provenance_locator,
                    }
                    for item in message.evidence
                ],
            }
            for message in value.messages
        ],
    }


def _outcome(value: GroundingOutcome) -> dict[str, object]:
    if isinstance(value, GroundedAnswer):
        return {
            "outcome": "GroundedAnswer",
            "answer": value.answer,
            "evidence": [
                {
                    "source_id": item.source_id.value,
                    "content": item.content,
                    "provenance_locator": item.provenance_locator,
                }
                for item in value.evidence
            ],
        }
    if isinstance(value, InsufficientEvidence):
        return {"outcome": "InsufficientEvidence", "reason": value.reason}
    if isinstance(value, PolicyDenied):
        return {"outcome": "PolicyDenied", "reason": value.reason}
    if isinstance(value, TechnicalFailure):
        return {
            "outcome": "TechnicalFailure",
            "reason": "request could not be completed",
        }
    raise TypeError("unsupported grounding outcome")


def create_system_conversation_router(
    service: SystemConversationControlPort,
) -> APIRouter:
    router = APIRouter(prefix="/api/system/conversations")

    def actor(request: Request) -> UUID:
        return cast(UUID, request.state.user.id)

    @router.get("")
    def conversations(
        request: Request,
        status: Literal["ACTIVE", "ARCHIVED", "ALL"] = "ACTIVE",
    ) -> list[dict[str, object]]:
        selected = None if status == "ALL" else SystemConversationStatus(status)
        return [_payload(item) for item in service.list(actor(request), status=selected)]

    @router.post("", status_code=201)
    def create(
        payload: SystemConversationCreateInput,
        request: Request,
    ) -> dict[str, object]:
        try:
            return _payload(
                service.create(
                    actor(request),
                    workspace_id=payload.workspace_id,
                    assistant_id=payload.assistant_id,
                    title=payload.title,
                )
            )
        except LookupError as exc:
            raise HTTPException(404, "workspace or assistant not found") from exc

    @router.get("/{conversation_id}")
    def detail(conversation_id: UUID, request: Request) -> dict[str, object]:
        try:
            return _payload(service.get(actor(request), conversation_id))
        except LookupError:
            raise HTTPException(404, "system conversation not found") from None

    @router.patch("/{conversation_id}/title")
    def rename(
        conversation_id: UUID,
        payload: SystemConversationRenameInput,
        request: Request,
    ) -> dict[str, object]:
        try:
            return _payload(
                service.rename(actor(request), conversation_id, title=payload.title)
            )
        except LookupError:
            raise HTTPException(404, "system conversation not found") from None

    @router.patch("/{conversation_id}/archive")
    def archive(
        conversation_id: UUID,
        payload: SystemConversationArchiveInput,
        request: Request,
    ) -> dict[str, object]:
        try:
            return _payload(
                service.set_archived(
                    actor(request),
                    conversation_id,
                    archived=payload.archived,
                )
            )
        except LookupError:
            raise HTTPException(404, "system conversation not found") from None

    @router.post("/{conversation_id}/ask")
    def ask(
        conversation_id: UUID,
        payload: SystemConversationAskInput,
        request: Request,
    ) -> dict[str, object]:
        try:
            return _outcome(
                service.ask(actor(request), conversation_id, question=payload.question)
            )
        except LookupError:
            raise HTTPException(404, "system conversation resource not found") from None
        except SystemConversationConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except WorkspaceOperationalError as exc:
            raise HTTPException(409, str(exc)) from None
        except AccessDenied:
            raise
        except Exception as exc:
            logger.error(
                "system_conversation_ask_failed conversation_id=%s exception_type=%s",
                conversation_id,
                type(exc).__name__,
            )
            raise HTTPException(500, "request could not be completed") from None

    return router
