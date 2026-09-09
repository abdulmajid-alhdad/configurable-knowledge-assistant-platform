"""SYSTEM-scoped, read-only provider usage telemetry delivery."""

from fastapi import APIRouter, HTTPException, Request

from knowledge_platform.application.provider_usage import (
    ProviderUsageControlPort,
    ProviderUsageUnavailable,
)


def create_provider_usage_router(service: ProviderUsageControlPort) -> APIRouter:
    router = APIRouter(prefix="/api/system/usage")

    @router.get("/provider")
    def provider_usage(request: Request) -> dict[str, object]:
        try:
            return service.summary(request.state.user.id)
        except ProviderUsageUnavailable as exc:
            detail = (
                "provider usage credential unavailable"
                if exc.category == "credential"
                else "provider usage telemetry unavailable"
            )
            raise HTTPException(
                status_code=503,
                detail=detail,
            ) from None

    return router
