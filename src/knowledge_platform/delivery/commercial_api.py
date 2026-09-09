"""Stage 7C commercial and advanced administration API."""

import re
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from knowledge_platform.application.commercial import CommercialPort


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list, max_length=20)
    expires_at: datetime | None = None


class SecurityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_keys_enabled: bool
    invitations_enabled: bool
    max_invitation_expiry_days: int = Field(ge=1, le=90)


class WorkspaceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=160)
    locale: str = Field(default="ar", min_length=2, max_length=16)
    timezone: str = Field(default="Asia/Riyadh", min_length=1, max_length=64)
    commercial_contact: str | None = Field(default=None, max_length=320)


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_code: str = Field(min_length=2, max_length=40)
    state: str = Field(min_length=3, max_length=20)


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    administrative_status: str = Field(min_length=3, max_length=20)
    base_url_override: str | None = Field(default=None, max_length=500)


class CredentialReferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,79}$")
    provider_code: str | None = Field(default=None, max_length=60)
    secret_reference: SecretStr
    status: str = Field(default="configured", min_length=3, max_length=20)

    @field_validator("secret_reference")
    @classmethod
    def validate_reference(cls, value: SecretStr) -> SecretStr:
        reference = value.get_secret_value()
        if re.fullmatch(
            r"(?:env:[A-Z][A-Z0-9_]{1,79}|vault:[A-Za-z0-9_./-]{1,180})",
            reference,
        ) is None:
            raise ValueError("credential reference must use env: or vault:")
        return value


def create_commercial_router(service: CommercialPort, *, system: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api/system" if system else "/api")

    def user(request: Request) -> UUID:
        return cast(UUID, request.state.user.id)

    @router.get("/workspaces/{workspace_id}/plans")
    def plans(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return service.plans(user(request), workspace_id)

    @router.get("/workspaces/{workspace_id}/subscription")
    def subscription(workspace_id: UUID, request: Request) -> dict[str, object]:
        return service.subscription(user(request), workspace_id)

    @router.get("/workspaces/{workspace_id}/entitlements")
    def entitlements(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return service.entitlements(user(request), workspace_id)

    @router.patch("/workspaces/{workspace_id}/subscription", status_code=204)
    def update_subscription(
        workspace_id: UUID, payload: SubscriptionUpdate, request: Request
    ) -> None:
        service.update_subscription(user(request), workspace_id, payload.plan_code, payload.state)

    @router.get("/workspaces/{workspace_id}/providers")
    def providers(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return service.providers(user(request), workspace_id)

    @router.patch("/workspaces/{workspace_id}/providers/{provider_code}", status_code=204)
    def update_provider(
        workspace_id: UUID, provider_code: str, payload: ProviderUpdate, request: Request,
    ) -> None:
        service.update_provider(
            user(request), workspace_id, provider_code, **payload.model_dump()
        )

    @router.get("/workspaces/{workspace_id}/credentials")
    def credentials(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return service.credentials(user(request), workspace_id)

    @router.post("/workspaces/{workspace_id}/credentials", status_code=201)
    def save_credential(
        workspace_id: UUID, payload: CredentialReferenceInput, request: Request,
    ) -> dict[str, UUID]:
        return {
            "id": service.save_credential_reference(
                user(request), workspace_id, name=payload.name,
                provider_code=payload.provider_code,
                secret_reference=payload.secret_reference.get_secret_value(),
                status=payload.status,
            )
        }

    @router.delete("/workspaces/{workspace_id}/credentials/{reference_id}", status_code=204)
    def delete_credential(workspace_id: UUID, reference_id: UUID, request: Request) -> None:
        service.delete_credential_reference(user(request), workspace_id, reference_id)

    @router.get("/workspaces/{workspace_id}/security")
    def security(workspace_id: UUID, request: Request) -> dict[str, object]:
        return service.security(user(request), workspace_id)

    @router.get("/workspaces/{workspace_id}/settings")
    def settings(workspace_id: UUID, request: Request) -> dict[str, object]:
        return service.settings(user(request), workspace_id)

    @router.patch("/workspaces/{workspace_id}/security", status_code=204)
    def update_security(workspace_id: UUID, payload: SecurityUpdate, request: Request) -> None:
        service.update_security(user(request), workspace_id, **payload.model_dump())

    @router.patch("/workspaces/{workspace_id}/settings", status_code=204)
    def update_settings(
        workspace_id: UUID, payload: WorkspaceSettingsUpdate, request: Request
    ) -> None:
        service.update_settings(user(request), workspace_id, **payload.model_dump())

    @router.get("/workspaces/{workspace_id}/api-keys")
    def api_keys(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return service.api_keys(user(request), workspace_id)

    @router.post("/workspaces/{workspace_id}/api-keys", status_code=201)
    def create_api_key(
        workspace_id: UUID, payload: ApiKeyCreate, request: Request
    ) -> dict[str, object]:
        return service.create_api_key(
            user(request),
            workspace_id,
            payload.name,
            payload.scopes,
            payload.expires_at,
        )

    @router.delete("/workspaces/{workspace_id}/api-keys/{key_id}", status_code=204)
    def revoke_api_key(workspace_id: UUID, key_id: UUID, request: Request) -> None:
        service.revoke_api_key(user(request), workspace_id, key_id)

    return router
