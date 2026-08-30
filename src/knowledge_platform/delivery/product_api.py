"""Typed workspace, assistant, and knowledge-source management API."""
# ruff: noqa: E501

from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)


class AssistantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    description: str | None = None
    instructions: str = Field(min_length=1)
    language: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_reference: str = Field(min_length=1)


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str


class AssistantResponse(AssistantInput):
    id: UUID
    workspace_id: UUID


class SourceResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    kind: str
    lifecycle: str


class ManagementServices(Protocol):
    def create_workspace(self, name: str) -> Workspace: ...
    def get_workspace(self, workspace_id: UUID) -> Workspace | None: ...
    def create_assistant(self, workspace_id: UUID, payload: AssistantInput) -> Assistant: ...
    def list_assistants(self, workspace_id: UUID) -> list[Assistant]: ...
    def get_assistant(self, workspace_id: UUID, assistant_id: UUID) -> Assistant | None: ...
    def update_assistant(self, workspace_id: UUID, assistant_id: UUID, payload: AssistantInput) -> Assistant: ...
    def create_source(self, workspace_id: UUID, payload: SourceCreate) -> KnowledgeSource: ...
    def list_sources(self, workspace_id: UUID) -> list[KnowledgeSource]: ...
    def get_source(self, workspace_id: UUID, source_id: UUID) -> KnowledgeSource | None: ...


def _workspace(value: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(id=value.id.value, name=value.name)


def _assistant(value: Assistant) -> AssistantResponse:
    return AssistantResponse(
        id=value.id.value, workspace_id=value.workspace_id.value,
        name=value.name, description=value.description, instructions=value.instructions,
        language=value.language, provider=value.model_configuration.provider,
        model_reference=value.model_configuration.model_reference,
    )


def _source(value: KnowledgeSource) -> SourceResponse:
    return SourceResponse(
        id=value.id.value, workspace_id=value.workspace_id.value, name=value.name,
        kind=value.kind.value, lifecycle=value.lifecycle.value,
    )


def create_management_router(services: ManagementServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
    def create_workspace(payload: WorkspaceCreate) -> WorkspaceResponse:
        return _workspace(services.create_workspace(payload.name))

    @router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    def get_workspace(workspace_id: UUID) -> WorkspaceResponse:
        value = services.get_workspace(workspace_id)
        if value is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        return _workspace(value)

    @router.post("/workspaces/{workspace_id}/assistants", response_model=AssistantResponse, status_code=201)
    def create_assistant(workspace_id: UUID, payload: AssistantInput) -> AssistantResponse:
        try:
            return _assistant(services.create_assistant(workspace_id, payload))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="workspace not found") from exc

    @router.get("/workspaces/{workspace_id}/assistants", response_model=list[AssistantResponse])
    def list_assistants(workspace_id: UUID) -> list[AssistantResponse]:
        return [_assistant(item) for item in services.list_assistants(workspace_id)]

    @router.get("/workspaces/{workspace_id}/assistants/{assistant_id}", response_model=AssistantResponse)
    def get_assistant(workspace_id: UUID, assistant_id: UUID) -> AssistantResponse:
        value = services.get_assistant(workspace_id, assistant_id)
        if value is None:
            raise HTTPException(status_code=404, detail="assistant not found")
        return _assistant(value)

    @router.patch("/workspaces/{workspace_id}/assistants/{assistant_id}", response_model=AssistantResponse)
    def update_assistant(workspace_id: UUID, assistant_id: UUID, payload: AssistantInput) -> AssistantResponse:
        try:
            return _assistant(services.update_assistant(workspace_id, assistant_id, payload))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant not found") from exc

    @router.post("/workspaces/{workspace_id}/sources", response_model=SourceResponse, status_code=201)
    def create_source(workspace_id: UUID, payload: SourceCreate) -> SourceResponse:
        try:
            return _source(services.create_source(workspace_id, payload))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unsupported source kind") from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="workspace not found") from exc

    @router.get("/workspaces/{workspace_id}/sources", response_model=list[SourceResponse])
    def list_sources(workspace_id: UUID) -> list[SourceResponse]:
        return [_source(item) for item in services.list_sources(workspace_id)]

    @router.get("/workspaces/{workspace_id}/sources/{source_id}", response_model=SourceResponse)
    def get_source(workspace_id: UUID, source_id: UUID) -> SourceResponse:
        value = services.get_source(workspace_id, source_id)
        if value is None:
            raise HTTPException(status_code=404, detail="source not found")
        return _source(value)

    @router.post("/workspaces/{workspace_id}/sources/{source_id}/upload")
    async def upload_source(workspace_id: UUID, source_id: UUID, request: Request) -> dict[str, object]:
        method = getattr(services, "upload_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="ingestion service unavailable")
        filename = request.headers.get("x-file-name", "")
        try:
            artifact = await method(workspace_id, source_id, request.stream(), filename, request.headers.get("content-type"))
            return {"artifact_present": True, "original_filename": artifact.original_filename,
                    "byte_size": artifact.byte_size, "sha256": artifact.sha256,
                    "suffix": artifact.suffix, "media_type": artifact.media_type}
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="source not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/workspaces/{workspace_id}/sources/{source_id}/process", response_model=SourceResponse)
    def process_source(workspace_id: UUID, source_id: UUID) -> SourceResponse:
        method = getattr(services, "process_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="ingestion service unavailable")
        try:
            return _source(method(workspace_id, source_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail="original artifact is not stored") from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="source not found") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="source processing failed") from exc

    @router.get("/workspaces/{workspace_id}/assistants/{assistant_id}/sources")
    def list_attached_sources(workspace_id: UUID, assistant_id: UUID) -> list[SourceResponse]:
        method = getattr(services, "list_attached_sources", None)
        if method is None:
            raise HTTPException(status_code=503, detail="scope service unavailable")
        return [_source(item) for item in method(workspace_id, assistant_id)]

    @router.post("/workspaces/{workspace_id}/assistants/{assistant_id}/sources/{source_id}", status_code=204)
    def attach_source(workspace_id: UUID, assistant_id: UUID, source_id: UUID) -> None:
        method = getattr(services, "attach_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="scope service unavailable")
        try:
            method(workspace_id, assistant_id, source_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant or source not found") from exc

    @router.delete("/workspaces/{workspace_id}/assistants/{assistant_id}/sources/{source_id}", status_code=204)
    def detach_source(workspace_id: UUID, assistant_id: UUID, source_id: UUID) -> None:
        method = getattr(services, "detach_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="scope service unavailable")
        method(workspace_id, assistant_id, source_id)

    return router
