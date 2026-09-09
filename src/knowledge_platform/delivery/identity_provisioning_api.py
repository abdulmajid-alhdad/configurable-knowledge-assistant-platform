"""System provisioning and pre-auth activation-only HTTP delivery."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from knowledge_platform.application.access_control import AccessConflict
from knowledge_platform.application.identity_provisioning import (
    IdentityProvisioningFailure,
    IdentityProvisioningService,
)


class ProvisionIdentityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr
    workspace_id: UUID
    role_id: UUID
    team_id: UUID | None = None
    expires_in_days: int = Field(default=7, ge=1, le=90)


class ActivationTokenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr


def _same_origin(request: Request) -> None:
    expected = str(request.base_url).rstrip("/")
    if (
        request.headers.get("origin") != expected
        and request.headers.get("sec-fetch-site") != "same-origin"
    ):
        raise HTTPException(403, "request origin rejected")


def _provisioning_error(code: str) -> HTTPException:
    status = 409
    if code in {"PROVISIONING_INPUT_INVALID", "IDENTITY_INPUT_REJECTED"}:
        status = 422
    elif code == "IDENTITY_ADMIN_PERMISSION_DENIED":
        status = 403
    elif code == "WORKSPACE_NOT_FOUND":
        status = 404
    elif code == "IDENTITY_ADMIN_NOT_CONFIGURED":
        status = 503
    elif code in {
        "IDENTITY_PROVIDER_FAILURE",
        "IDENTITY_PROVIDER_MALFORMED",
        "PLATFORM_PERSISTENCE_FAILED",
        "IDENTITY_COMPENSATION_FAILED",
    }:
        status = 502
    return HTTPException(status, code)


def _activation_error(code: str) -> HTTPException:
    status = 409
    if code in {"INVITATION_INVALID", "INVITATION_NOT_ACTIVATABLE"}:
        status = 404
    elif code == "INVITATION_EXPIRED":
        status = 410
    elif code == "IDENTITY_ADMIN_NOT_CONFIGURED":
        status = 503
    elif code in {
        "IDENTITY_PROVIDER_FAILURE",
        "IDENTITY_PROVIDER_MALFORMED",
        "PROVISIONED_IDENTITY_MISSING",
    }:
        status = 502
    return HTTPException(status, code)


def create_identity_provisioning_router(
    service: IdentityProvisioningService,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/system/identity/provision", status_code=201)
    def provision(
        payload: ProvisionIdentityInput, request: Request
    ) -> dict[str, object]:
        try:
            invitation = service.provision(
                request.state.user.id,
                display_name=payload.username,
                email=payload.email,
                password=payload.password.get_secret_value(),
                workspace_id=payload.workspace_id,
                role_id=payload.role_id,
                team_id=payload.team_id,
                expires_in_days=payload.expires_in_days,
            )
        except AccessConflict as error:
            raise _provisioning_error(str(error)) from None
        except IdentityProvisioningFailure as error:
            raise _provisioning_error(error.code) from None
        return {
            "id": invitation.invitation_id,
            "workspace_id": invitation.workspace_id,
            "user_id": invitation.user_id,
            "team_id": invitation.team_id,
            "status": invitation.status,
            "created_at": invitation.created_at,
            "expires_at": invitation.expires_at,
            # This is the only response that contains the raw one-time token.
            "activation_path": invitation.activation_path,
        }

    @router.post("/api/auth/invitations/activation/preview")
    def preview(
        payload: ActivationTokenInput, request: Request
    ) -> dict[str, object]:
        _same_origin(request)
        try:
            invitation = service.preview(payload.token.get_secret_value())
        except IdentityProvisioningFailure as error:
            raise _activation_error(error.code) from None
        return {
            "workspace_name": invitation.workspace_name,
            "username": invitation.display_name,
            "email": invitation.email,
            "role_name": invitation.role_name,
            "team_name": invitation.team_name,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
        }

    @router.post("/api/auth/invitations/activation")
    def activate(
        payload: ActivationTokenInput, request: Request
    ) -> dict[str, object]:
        _same_origin(request)
        try:
            service.activate(payload.token.get_secret_value())
        except IdentityProvisioningFailure as error:
            raise _activation_error(error.code) from None
        # Deliberately no session, cookie, bearer token, or authenticated redirect.
        return {
            "message": "تم تفعيل الحساب، يمكنك الآن تسجيل الدخول.",
            "login_path": "/login",
        }

    return router
