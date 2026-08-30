"""Persisted conversation and assistant ask endpoints."""
from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.evidence_grounding.domain.contracts import GroundedAnswer, InsufficientEvidence, PolicyDenied, TechnicalFailure


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)


class ConversationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    assistant_id: UUID
    messages: list[dict[str, object]]


class ConversationServices(Protocol):
    def create_conversation(self, workspace_id: UUID, assistant_id: UUID) -> Conversation: ...
    def get_conversation(self, workspace_id: UUID, conversation_id: UUID) -> Conversation | None: ...
    def ask_conversation(self, workspace_id: UUID, conversation_id: UUID, question: str) -> object: ...


def _conversation(value: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=value.id.value, workspace_id=value.workspace_id.value, assistant_id=value.assistant_id.value,
        messages=[{"sequence": m.sequence, "role": m.role.value, "content": m.content} for m in value.messages],
    )


def _outcome(value: object) -> dict[str, object]:
    if isinstance(value, GroundedAnswer):
        return {"outcome": "GroundedAnswer", "answer": value.answer, "evidence": [
            {"source_id": str(item.source_id.value), "content": item.content,
             "provenance_locator": item.provenance_locator} for item in value.evidence
        ]}
    if isinstance(value, InsufficientEvidence):
        return {"outcome": "InsufficientEvidence", "reason": value.reason}
    if isinstance(value, PolicyDenied):
        return {"outcome": "PolicyDenied", "reason": value.reason}
    if isinstance(value, TechnicalFailure):
        return {"outcome": "TechnicalFailure", "reason": "request could not be completed"}
    return {"outcome": "TechnicalFailure", "reason": "request could not be completed"}


def create_conversation_router(services: ConversationServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/workspaces/{workspace_id}/assistants/{assistant_id}/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
    def create(workspace_id: UUID, assistant_id: UUID) -> ConversationResponse:
        try:
            return _conversation(services.create_conversation(workspace_id, assistant_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant not found") from exc

    @router.get("/workspaces/{workspace_id}/conversations/{conversation_id}", response_model=ConversationResponse)
    def get(workspace_id: UUID, conversation_id: UUID) -> ConversationResponse:
        value = services.get_conversation(workspace_id, conversation_id)
        if value is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return _conversation(value)

    @router.post("/workspaces/{workspace_id}/conversations/{conversation_id}/ask")
    def ask(workspace_id: UUID, conversation_id: UUID, payload: QuestionInput) -> dict[str, object]:
        try:
            return _outcome(services.ask_conversation(workspace_id, conversation_id, payload.question))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="conversation not found") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="request could not be completed") from exc

    return router
