"""Application port and stable policy failure for Control Plane administration."""

from datetime import datetime
from typing import Protocol
from uuid import UUID


class GovernanceBlocked(RuntimeError):
    """An enforceable Workspace governance policy blocks an operation."""


class AdministrationPort(Protocol):
    def usage(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        days: int = 30,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]: ...

    def governance(
        self, user_id: UUID, workspace_id: UUID
    ) -> list[dict[str, object]]: ...

    def governance_enabled(
        self, user_id: UUID, workspace_id: UUID, key: str
    ) -> bool: ...

    def require_governance(
        self, user_id: UUID, workspace_id: UUID, key: str
    ) -> None: ...

    def update_governance(
        self,
        user_id: UUID,
        workspace_id: UUID,
        key: str,
        enabled: bool,
        request_id: str | None = None,
    ) -> None: ...

    def audit(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, object]]: ...

    def notifications(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]: ...

    def mark_notifications_read(
        self,
        user_id: UUID,
        workspace_id: UUID,
        notification_id: UUID | None = None,
    ) -> None: ...

    def operations(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, object]]: ...

    def record_usage(
        self,
        user_id: UUID,
        workspace_id: UUID,
        event_type: str,
        unit: str,
        *,
        quantity: int | float = 1,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None: ...

    def record_audit(
        self,
        user_id: UUID,
        workspace_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID | None,
        *,
        outcome: str = "succeeded",
        request_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_operation(
        self,
        user_id: UUID,
        workspace_id: UUID,
        operation_type: str,
        status: str,
        resource_type: str | None,
        resource_id: UUID | None,
        started_at: datetime,
        safe_error_category: str | None = None,
    ) -> None: ...
