"""Delivery boundary for the distinct SYSTEM Conversation aggregate."""

from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowledge_platform.application.system_conversations import (
    SystemConversationControlPort,
)
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)


class SystemConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("system conversation title is blank")
        return normalized


class SystemConversationArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool


def _payload(value: SystemConversation) -> dict[str, object]:
    return {
        "id": value.id,
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
            }
            for message in value.messages
        ],
    }


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
        payload: SystemConversationInput,
        request: Request,
    ) -> dict[str, object]:
        return _payload(service.create(actor(request), title=payload.title))

    @router.get("/{conversation_id}")
    def detail(conversation_id: UUID, request: Request) -> dict[str, object]:
        try:
            return _payload(service.get(actor(request), conversation_id))
        except LookupError:
            raise HTTPException(404, "system conversation not found") from None

    @router.patch("/{conversation_id}/title")
    def rename(
        conversation_id: UUID,
        payload: SystemConversationInput,
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
                    actor(request), conversation_id, archived=payload.archived
                )
            )
        except LookupError:
            raise HTTPException(404, "system conversation not found") from None

    return router
