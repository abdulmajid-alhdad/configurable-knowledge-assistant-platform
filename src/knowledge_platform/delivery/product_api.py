"""Typed workspace, assistant, and knowledge-source management API."""
# ruff: noqa: E501

import logging
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from urllib.parse import unquote_to_bytes
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.application.administration import AdministrationPort, GovernanceBlocked
from knowledge_platform.application.workspace_operational_state import (
    WorkspaceOperationalError,
)
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.document_knowledge.artifacts import (
    OriginalArtifactIntegrityError,
)
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

logger = logging.getLogger(__name__)


def _log_processing_failure(*, workspace_id: UUID, source_id: UUID, error: Exception) -> None:
    """Log failure location and category without serializing provider/SQL details."""
    logger.error(
        "knowledge_source_processing_failed",
        extra={
            "workspace_id": str(workspace_id),
            "source_id": str(source_id),
            "exception_type": type(error).__name__,
        },
    )


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    ai_execution_enabled: bool = True


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
    operational_status: str = "ACTIVE"
    ai_execution_enabled: bool = True


class AssistantResponse(AssistantInput):
    id: UUID
    workspace_id: UUID


class SourceResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    kind: str
    lifecycle: str


class SourceArtifactResponse(BaseModel):
    artifact_present: bool
    artifact_state: Literal[
        "AWAITING_UPLOAD", "STORED", "LEGACY_UNAVAILABLE", "UNAVAILABLE"
    ]
    upload_allowed: bool
    original_filename: str | None = None
    suffix: str | None = None
    media_type: str | None = None
    byte_size: int | None = None
    stored_at: datetime | None = None


class ManagementServices(Protocol):
    def create_workspace(
        self, name: str, *, ai_execution_enabled: bool = True
    ) -> Workspace: ...
    def get_workspace(self, workspace_id: UUID) -> Workspace | None: ...
    def create_assistant(self, workspace_id: UUID, payload: AssistantInput) -> Assistant: ...
    def list_assistants(self, workspace_id: UUID) -> list[Assistant]: ...
    def get_assistant(self, workspace_id: UUID, assistant_id: UUID) -> Assistant | None: ...
    def update_assistant(self, workspace_id: UUID, assistant_id: UUID, payload: AssistantInput) -> Assistant: ...
    def create_source(
        self,
        workspace_id: UUID,
        payload: SourceCreate,
        *,
        system_operation: bool = False,
    ) -> KnowledgeSource: ...
    def list_sources(self, workspace_id: UUID) -> list[KnowledgeSource]: ...
    def get_source(self, workspace_id: UUID, source_id: UUID) -> KnowledgeSource | None: ...


def _workspace(value: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=value.id.value,
        name=value.name,
        operational_status=value.operational_status.value,
        ai_execution_enabled=value.ai_execution_enabled,
    )


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


def create_management_router(
    services: ManagementServices, access: AccessControlPort | None = None,
    administration: AdministrationPort | None = None, *, system: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="/api/system" if system else "/api")

    @router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
    def create_workspace(payload: WorkspaceCreate, request: Request) -> WorkspaceResponse:
        if access is None:
            return _workspace(
                services.create_workspace(
                    payload.name,
                    ai_execution_enabled=payload.ai_execution_enabled,
                )
            )
        value = access.create_workspace(
            request.state.user.id,
            payload.name,
            ai_execution_enabled=payload.ai_execution_enabled,
        )
        workspace_id = cast(UUID, value["id"])
        return WorkspaceResponse(
            id=workspace_id,
            name=str(value["name"]),
            operational_status=str(value.get("operational_status", "ACTIVE")),
            ai_execution_enabled=bool(value.get("ai_execution_enabled", True)),
        )

    @router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    def get_workspace(workspace_id: UUID) -> WorkspaceResponse:
        value = services.get_workspace(workspace_id)
        if value is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        return _workspace(value)

    @router.post("/workspaces/{workspace_id}/assistants", response_model=AssistantResponse, status_code=201)
    def create_assistant(
        workspace_id: UUID, payload: AssistantInput, request: Request,
    ) -> AssistantResponse:
        try:
            if access is not None:
                access.require_system(request.state.user.id, Permission.ASSISTANT_CREATE)
            value = services.create_assistant(workspace_id, payload)
            return _assistant(value)
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
    def update_assistant(
        workspace_id: UUID, assistant_id: UUID, payload: AssistantInput, request: Request,
    ) -> AssistantResponse:
        try:
            if access is not None:
                access.require_system(request.state.user.id, Permission.ASSISTANT_UPDATE)
            value = services.update_assistant(workspace_id, assistant_id, payload)
            return _assistant(value)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant not found") from exc

    @router.post("/workspaces/{workspace_id}/sources", response_model=SourceResponse, status_code=201)
    def create_source(
        workspace_id: UUID, payload: SourceCreate, request: Request,
    ) -> SourceResponse:
        try:
            if administration is not None and not system:
                administration.require_governance(
                    request.state.user.id,
                    workspace_id,
                    "knowledge_source_addition_enabled",
                )
            value = (
                services.create_source(
                    workspace_id,
                    payload,
                    system_operation=True,
                )
                if system
                else services.create_source(workspace_id, payload)
            )
            return _source(value)
        except GovernanceBlocked as exc:
            raise HTTPException(
                status_code=409, detail="knowledge source addition is disabled"
            ) from exc
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

    @router.get(
        "/workspaces/{workspace_id}/sources/{source_id}/artifact",
        response_model=SourceArtifactResponse,
    )
    def get_source_artifact(
        workspace_id: UUID, source_id: UUID
    ) -> SourceArtifactResponse:
        method = getattr(services, "get_source_artifact", None)
        if method is None:
            raise HTTPException(status_code=503, detail="ingestion service unavailable")
        try:
            source = services.get_source(workspace_id, source_id)
            if source is None:
                raise LookupError("source not found")
            artifact = method(workspace_id, source_id)
        except OriginalArtifactIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="original artifact storage is incomplete",
            ) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="source not found") from exc
        if artifact is None:
            upload_allowed = source.lifecycle.value in {"registered", "failed", "ready"}
            artifact_state: Literal[
                "AWAITING_UPLOAD", "STORED", "LEGACY_UNAVAILABLE", "UNAVAILABLE"
            ] = (
                "AWAITING_UPLOAD"
                if source.lifecycle.value in {"registered", "failed"}
                else "LEGACY_UNAVAILABLE"
                if source.lifecycle.value == "ready"
                else "UNAVAILABLE"
            )
            return SourceArtifactResponse(
                artifact_present=False,
                artifact_state=artifact_state,
                upload_allowed=upload_allowed,
            )
        return SourceArtifactResponse(
            artifact_present=True,
            artifact_state="STORED",
            upload_allowed=False,
            original_filename=artifact.original_filename,
            suffix=artifact.suffix,
            media_type=artifact.media_type,
            byte_size=artifact.byte_size,
            stored_at=artifact.stored_at,
        )

    @router.post(
        "/workspaces/{workspace_id}/sources/{source_id}/upload",
        response_model=SourceArtifactResponse,
    )
    async def upload_source(
        workspace_id: UUID, source_id: UUID, request: Request
    ) -> SourceArtifactResponse:
        method = getattr(services, "upload_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="ingestion service unavailable")
        encoded_filename = request.headers.get("x-file-name", "")
        try:
            filename = (
                unquote_to_bytes(encoded_filename).decode("utf-8")
                if request.headers.get("x-file-name-encoding") == "percent"
                else encoded_filename
            )
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid original filename") from exc
        try:
            if administration is not None and not system:
                administration.require_governance(
                    request.state.user.id,
                    workspace_id,
                    "knowledge_source_addition_enabled",
                )
            artifact = (
                await method(
                    workspace_id,
                    source_id,
                    request.stream(),
                    filename,
                    request.headers.get("content-type"),
                    system_operation=True,
                )
                if system
                else await method(
                    workspace_id,
                    source_id,
                    request.stream(),
                    filename,
                    request.headers.get("content-type"),
                )
            )
        except GovernanceBlocked as exc:
            raise HTTPException(
                status_code=409, detail="knowledge source addition is disabled"
            ) from exc
        except OriginalArtifactIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="original artifact storage is incomplete",
            ) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="source not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            logger.error(
                "original_artifact_storage_failed",
                extra={
                    "workspace_id": str(workspace_id),
                    "source_id": str(source_id),
                    "exception_type": type(exc).__name__,
                },
            )
            raise HTTPException(
                status_code=503, detail="original artifact storage unavailable"
            ) from exc
        if administration is not None:
            try:
                administration.record_usage(
                    request.state.user.id, workspace_id, "artifact.stored", "bytes",
                    quantity=artifact.byte_size, resource_type="knowledge_source",
                    resource_id=source_id,
                )
                administration.record_audit(
                    request.state.user.id, workspace_id, "artifact.stored",
                    "knowledge_source", source_id,
                    request_id=request.headers.get("x-request-id"),
                )
            except Exception as exc:
                logger.error(
                    "original_artifact_administration_record_failed",
                    extra={
                        "workspace_id": str(workspace_id),
                        "source_id": str(source_id),
                        "exception_type": type(exc).__name__,
                    },
                )
        return SourceArtifactResponse(
            artifact_present=True,
            artifact_state="STORED",
            upload_allowed=False,
            original_filename=artifact.original_filename,
            byte_size=artifact.byte_size,
            suffix=artifact.suffix,
            media_type=artifact.media_type,
            stored_at=artifact.stored_at,
        )

    @router.post("/workspaces/{workspace_id}/sources/{source_id}/process", response_model=SourceResponse)
    def process_source(workspace_id: UUID, source_id: UUID, request: Request) -> SourceResponse:
        method = getattr(services, "process_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="ingestion service unavailable")
        started = datetime.now(UTC)
        try:
            if administration is not None and not system:
                administration.require_governance(
                    request.state.user.id, workspace_id, "knowledge_processing_enabled"
                )
            value = (
                method(workspace_id, source_id, system_operation=True)
                if system
                else method(workspace_id, source_id)
            )
        except GovernanceBlocked as exc:
            raise HTTPException(status_code=409, detail="source processing is disabled") from exc
        except WorkspaceOperationalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail="original artifact is not stored") from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="source not found") from exc
        except Exception as exc:
            _log_processing_failure(
                workspace_id=workspace_id, source_id=source_id, error=exc
            )
            if administration is not None and system:
                try:
                    administration.record_operation(
                        request.state.user.id,
                        workspace_id,
                        "source.processing",
                        "failed",
                        "knowledge_source",
                        source_id,
                        started,
                        type(exc).__name__,
                    )
                except Exception as record_error:
                    logger.error(
                        "source_processing_administration_record_failed",
                        extra={
                            "workspace_id": str(workspace_id),
                            "source_id": str(source_id),
                            "exception_type": type(record_error).__name__,
                        },
                    )
            raise HTTPException(status_code=422, detail="source processing failed") from exc
        if administration is not None:
            try:
                administration.record_usage(
                    request.state.user.id,
                    workspace_id,
                    "source.processing",
                    "operations",
                    resource_type="knowledge_source",
                    resource_id=source_id,
                )
                if system:
                    administration.record_operation(
                        request.state.user.id,
                        workspace_id,
                        "source.processing",
                        "succeeded",
                        "knowledge_source",
                        source_id,
                        started,
                    )
                administration.record_audit(
                    request.state.user.id,
                    workspace_id,
                    "knowledge_source.processed",
                    "knowledge_source",
                    source_id,
                    request_id=request.headers.get("x-request-id"),
                )
            except Exception as record_error:
                logger.error(
                    "source_processing_administration_record_failed",
                    extra={
                        "workspace_id": str(workspace_id),
                        "source_id": str(source_id),
                        "exception_type": type(record_error).__name__,
                    },
                )
        return _source(value)

    @router.get("/workspaces/{workspace_id}/assistants/{assistant_id}/sources")
    def list_attached_sources(workspace_id: UUID, assistant_id: UUID) -> list[SourceResponse]:
        method = getattr(services, "list_attached_sources", None)
        if method is None:
            raise HTTPException(status_code=503, detail="scope service unavailable")
        return [_source(item) for item in method(workspace_id, assistant_id)]

    @router.post("/workspaces/{workspace_id}/assistants/{assistant_id}/sources/{source_id}", status_code=204)
    def attach_source(
        workspace_id: UUID, assistant_id: UUID, source_id: UUID, request: Request,
    ) -> None:
        method = getattr(services, "attach_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="scope service unavailable")
        try:
            method(workspace_id, assistant_id, source_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="assistant or source not found") from exc

    @router.delete("/workspaces/{workspace_id}/assistants/{assistant_id}/sources/{source_id}", status_code=204)
    def detach_source(
        workspace_id: UUID, assistant_id: UUID, source_id: UUID, request: Request,
    ) -> None:
        method = getattr(services, "detach_source", None)
        if method is None:
            raise HTTPException(status_code=503, detail="scope service unavailable")
        method(workspace_id, assistant_id, source_id)

    return router
