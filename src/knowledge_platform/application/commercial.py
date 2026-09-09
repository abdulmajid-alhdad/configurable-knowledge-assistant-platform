"""Application port and safe errors for commercial administration."""

from datetime import datetime
from typing import Protocol
from uuid import UUID


class CommercialError(RuntimeError):
    """Stable, secret-safe commercial/administrative failure code."""


class CommercialPort(Protocol):
    def plans(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def subscription(self, user_id: UUID, workspace_id: UUID) -> dict[str, object]: ...

    def update_subscription(
        self, user_id: UUID, workspace_id: UUID, plan_code: str, state: str
    ) -> None: ...

    def entitlements(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def require_count_limit(
        self, user_id: UUID, workspace_id: UUID, key: str, current_count: int
    ) -> None: ...

    def providers(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def update_provider(
        self,
        user_id: UUID,
        workspace_id: UUID,
        provider_code: str,
        *,
        enabled: bool,
        administrative_status: str,
        base_url_override: str | None,
    ) -> None: ...

    def credentials(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def save_credential_reference(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        name: str,
        provider_code: str | None,
        secret_reference: str,
        status: str,
    ) -> UUID: ...

    def delete_credential_reference(
        self, user_id: UUID, workspace_id: UUID, reference_id: UUID
    ) -> None: ...

    def security(self, user_id: UUID, workspace_id: UUID) -> dict[str, object]: ...

    def settings(self, user_id: UUID, workspace_id: UUID) -> dict[str, object]: ...

    def api_keys(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def create_api_key(
        self,
        user_id: UUID,
        workspace_id: UUID,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> dict[str, object]: ...

    def revoke_api_key(
        self, user_id: UUID, workspace_id: UUID, key_id: UUID
    ) -> None: ...

    def authenticate_api_key(self, plaintext: str) -> dict[str, object] | None: ...

    def update_security(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        api_keys_enabled: bool,
        invitations_enabled: bool,
        max_invitation_expiry_days: int,
    ) -> None: ...

    def update_settings(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        display_name: str | None,
        locale: str,
        timezone: str,
        commercial_contact: str | None,
    ) -> None: ...
