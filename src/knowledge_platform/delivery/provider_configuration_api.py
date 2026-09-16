"""SYSTEM-only delivery for effective, secret-free provider configuration."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.provider_catalogue import (
    ProviderModelCatalogueControlPort,
    ProviderModelCatalogueError,
)
from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderConfigurationConflict,
    ProviderConfigurationControlPort,
    ProviderConfigurationError,
)


class RuntimeProviderConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=60)
    model_id: str = Field(min_length=1, max_length=240)
    endpoint: str = Field(min_length=1, max_length=500)
    credential_reference: str = Field(min_length=2, max_length=80)
    dimensions: int | None = Field(default=None, ge=1, le=65536)
    active: bool


def create_provider_configuration_router(
    service: ProviderConfigurationControlPort,
    catalogue: ProviderModelCatalogueControlPort,
) -> APIRouter:
    router = APIRouter(prefix="/api/system/providers")

    @router.get("/runtime")
    def runtime_configuration(request: Request) -> dict[str, object]:
        try:
            return service.runtime_configuration(request.state.user.id)
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

    @router.put("/runtime/{capability}")
    def configure_runtime(
        capability: ModelCapability,
        payload: RuntimeProviderConfigurationUpdate,
        request: Request,
    ) -> dict[str, object]:
        try:
            return service.configure(
                request.state.user.id,
                capability,
                provider=payload.provider,
                model_id=payload.model_id,
                endpoint=payload.endpoint,
                credential_reference=payload.credential_reference,
                dimensions=payload.dimensions,
                active=payload.active,
                request_id=request.headers.get("x-request-id"),
            )
        except ProviderConfigurationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.get("/{provider}/models")
    def provider_models(
        provider: str,
        capability: ModelCapability,
        request: Request,
    ) -> dict[str, object]:
        try:
            return catalogue.models(request.state.user.id, provider, capability)
        except ProviderModelCatalogueError as exc:
            code = str(exc)
            status = {
                "UNSUPPORTED_PROVIDER": 404,
                "PROVIDER_CAPABILITY_MISMATCH": 422,
            }.get(code, 503)
            raise HTTPException(status_code=status, detail=str(exc)) from None

    return router
