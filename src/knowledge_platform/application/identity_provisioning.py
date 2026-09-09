"""Backend-only identity provisioning and activation orchestration."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.modules.access_control.domain import Permission


class IdentityAdminFailure(RuntimeError):
    """Safe failure raised by the external identity administration boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IdentityProvisioningFailure(RuntimeError):
    """Stable, non-secret product failure for provisioning or activation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProvisionedIdentity:
    id: UUID
    email: str


@dataclass(frozen=True, slots=True)
class ProvisioningIntent:
    workspace_id: UUID
    display_name: str
    email: str
    role_id: UUID
    team_id: UUID | None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ProvisionedInvitation:
    invitation_id: UUID
    workspace_id: UUID
    user_id: UUID
    team_id: UUID | None
    status: str
    created_at: datetime
    expires_at: datetime
    activation_path: str


@dataclass(frozen=True, slots=True)
class ActivationPreview:
    invitation_id: UUID | None
    provisioned_user_id: UUID | None
    email: str | None
    display_name: str | None
    workspace_id: UUID | None
    workspace_name: str | None
    role_id: UUID | None
    role_name: str | None
    team_id: UUID | None
    team_name: str | None
    status: str | None
    expires_at: datetime | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class ActivationResult:
    workspace_id: UUID | None
    user_id: UUID | None
    team_id: UUID | None
    error_code: str | None


class IdentityAdminPort(Protocol):
    """Narrow server-only port for Supabase Auth administrative operations."""

    def create_unconfirmed_user(
        self, *, email: str, password: str, display_name: str
    ) -> ProvisionedIdentity: ...

    def confirm_user(self, user_id: UUID) -> None: ...

    def delete_user(self, user_id: UUID) -> None: ...


class IdentityProvisioningStorePort(Protocol):
    """Transactional platform-data boundary for provisioning intent."""

    def validate(self, actor: UUID, intent: ProvisioningIntent) -> None: ...

    def create(
        self,
        actor: UUID,
        identity: ProvisionedIdentity,
        intent: ProvisioningIntent,
        token_digest: str,
    ) -> dict[str, object]: ...

    def preview(self, token_digest: str) -> ActivationPreview: ...

    def activate(self, token_digest: str, user_id: UUID) -> ActivationResult: ...


class IdentityProvisioningService:
    """Coordinates non-transactional Auth Admin and transactional platform data."""

    _TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")

    def __init__(
        self,
        *,
        access: AccessControlPort,
        identity_admin: IdentityAdminPort,
        store: IdentityProvisioningStorePort,
    ) -> None:
        self._access = access
        self._identity_admin = identity_admin
        self._store = store

    @staticmethod
    def _digest(raw_token: str) -> str:
        if not IdentityProvisioningService._TOKEN.fullmatch(raw_token):
            raise IdentityProvisioningFailure("INVITATION_INVALID")
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def provision(
        self,
        actor: UUID,
        *,
        display_name: str,
        email: str,
        password: str,
        workspace_id: UUID,
        role_id: UUID,
        team_id: UUID | None,
        expires_in_days: int,
    ) -> ProvisionedInvitation:
        self._access.require_system(actor, Permission.INVITATIONS_MANAGE)
        normalized_name = display_name.strip()
        normalized_email = email.strip().casefold()
        if not normalized_name or len(normalized_name) > 120:
            raise IdentityProvisioningFailure("PROVISIONING_INPUT_INVALID")
        if (
            not normalized_email
            or len(normalized_email) > 320
            or "@" not in normalized_email
            or not 8 <= len(password) <= 256
            or not 1 <= expires_in_days <= 90
        ):
            raise IdentityProvisioningFailure("PROVISIONING_INPUT_INVALID")

        intent = ProvisioningIntent(
            workspace_id=workspace_id,
            display_name=normalized_name,
            email=normalized_email,
            role_id=role_id,
            team_id=team_id,
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
        )
        self._store.validate(actor, intent)
        try:
            identity = self._identity_admin.create_unconfirmed_user(
                email=normalized_email,
                password=password,
                display_name=normalized_name,
            )
        except IdentityAdminFailure as error:
            raise IdentityProvisioningFailure(error.code) from None

        raw_token = secrets.token_urlsafe(32)
        try:
            row = self._store.create(
                actor,
                identity,
                intent,
                hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            )
        except Exception:
            try:
                self._identity_admin.delete_user(identity.id)
            except IdentityAdminFailure:
                raise IdentityProvisioningFailure(
                    "IDENTITY_COMPENSATION_FAILED"
                ) from None
            raise IdentityProvisioningFailure("PLATFORM_PERSISTENCE_FAILED") from None

        return ProvisionedInvitation(
            invitation_id=UUID(str(row["created_invitation_id"])),
            workspace_id=UUID(str(row["created_workspace_id"])),
            user_id=UUID(str(row["created_user_id"])),
            team_id=(
                UUID(str(row["created_team_id"]))
                if row.get("created_team_id") is not None
                else None
            ),
            status=str(row["created_status"]),
            created_at=row["created_at"],  # type: ignore[arg-type]
            expires_at=row["expires_at"],  # type: ignore[arg-type]
            # The fragment is never sent in an HTTP request or access log.
            activation_path=f"/app/invitations/accept#token={raw_token}",
        )

    def preview(self, raw_token: str) -> ActivationPreview:
        result = self._store.preview(self._digest(raw_token))
        if result.error_code is not None:
            raise IdentityProvisioningFailure(result.error_code)
        return result

    def activate(self, raw_token: str) -> ActivationResult:
        digest = self._digest(raw_token)
        preview = self._store.preview(digest)
        if preview.error_code is not None or preview.provisioned_user_id is None:
            raise IdentityProvisioningFailure(
                preview.error_code or "INVITATION_INVALID"
            )
        try:
            # This is idempotent. If the following database transaction fails,
            # retrying the activation safely completes only the database side.
            self._identity_admin.confirm_user(preview.provisioned_user_id)
        except IdentityAdminFailure as error:
            raise IdentityProvisioningFailure(error.code) from None
        result = self._store.activate(digest, preview.provisioned_user_id)
        if result.error_code is not None:
            raise IdentityProvisioningFailure(result.error_code)
        return result
