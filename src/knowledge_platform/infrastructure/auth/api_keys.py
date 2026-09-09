"""Dedicated API-key principal adapter; separate from Supabase Auth users."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from knowledge_platform.application.commercial import CommercialPort


@dataclass(frozen=True, slots=True)
class ApiKeyPrincipal:
    key_id: UUID
    workspace_id: UUID
    scopes: tuple[str, ...]
    created_by: UUID

    def allows(self, permission: str) -> bool:
        """Authorize only an explicitly stored key scope."""
        return permission in self.scopes

    def require(self, permission: str) -> None:
        if not self.allows(permission):
            raise PermissionError("API_KEY_SCOPE_DENIED")


class ApiKeyAuthenticator:
    """Resolve a presented key without exposing hashes or plaintext values."""

    def __init__(self, commercial: CommercialPort) -> None:
        self._commercial = commercial

    def authenticate(self, presented_key: str) -> ApiKeyPrincipal | None:
        result = self._commercial.authenticate_api_key(presented_key)
        if result is None:
            return None
        key_id = result.get("key_id")
        if not isinstance(key_id, UUID):
            raise ValueError("malformed API key principal")
        workspace_id = result.get("workspace_id")
        if not isinstance(workspace_id, UUID):
            raise ValueError("malformed API key principal")
        created_by = result.get("created_by")
        if not isinstance(created_by, UUID):
            raise ValueError("malformed API key principal")
        raw_scopes = result.get("scopes")
        if not isinstance(raw_scopes, (list, tuple)):
            raise ValueError("malformed API key principal")
        scopes: list[str] = []
        for scope in raw_scopes:
            if not isinstance(scope, str):
                raise ValueError("malformed API key principal")
            scopes.append(scope)
        return ApiKeyPrincipal(
            key_id=key_id,
            workspace_id=workspace_id,
            scopes=tuple(scopes),
            created_by=created_by,
        )

    @staticmethod
    def bind_authorization_context(
        session: Session, principal: ApiKeyPrincipal, required_scope: str
    ) -> None:
        """Bind a dedicated API-key context after an explicit scope check.

        ``app.user_id`` is deliberately a nil UUID rather than ``created_by``:
        the API key never impersonates a Supabase user. Existing user RLS will
        consequently grant it nothing until a future key-aware port is
        deliberately added.
        """
        principal.require(required_scope)
        session.execute(
            text("select set_config('app.user_id', :value, true)"),
            {"value": str(UUID(int=0))},
        )
        session.execute(
            text("select set_config('app.workspace_id', :value, true)"),
            {"value": str(principal.workspace_id)},
        )
        session.execute(
            text("select set_config('app.api_key_id', :value, true)"),
            {"value": str(principal.key_id)},
        )
