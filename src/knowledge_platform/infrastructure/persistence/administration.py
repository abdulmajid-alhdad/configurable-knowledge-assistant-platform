"""SQLAlchemy adapter for administrative observability and governance."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import AccessNotFound
from knowledge_platform.application.administration import GovernanceBlocked
from knowledge_platform.infrastructure.persistence.access_control import (
    AccessControlService,
)
from knowledge_platform.modules.access_control.domain import Permission

_SENSITIVE_METADATA_TERMS = (
    "authorization",
    "credential",
    "dsn",
    "password",
    "secret",
    "token",
    "api_key",
)


def _safe_audit_metadata(value: object) -> object:
    """Preserve audit structure while removing secret-bearing fields."""
    if isinstance(value, dict):
        safe: dict[str, object] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            safe[str(key)] = (
                "[REDACTED]"
                if any(term in normalized for term in _SENSITIVE_METADATA_TERMS)
                else _safe_audit_metadata(item)
            )
        return safe
    if isinstance(value, list):
        return [_safe_audit_metadata(item) for item in value]
    return value


class AdministrationService:
    """Queries bounded administrative history and performs governed updates."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
        self._access = AccessControlService(sessions)

    @contextmanager
    def _tx(self, user_id: UUID, workspace_id: UUID) -> Iterator[Session]:
        with self._sessions.begin() as session:
            session.execute(
                text("select set_config('app.user_id', :value, true)"),
                {"value": str(user_id)},
            )
            session.execute(
                text("select set_config('app.workspace_id', :value, true)"),
                {"value": str(workspace_id)},
            )
            yield session

    def usage(
        self, user_id: UUID, workspace_id: UUID, *, days: int = 30,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, object]:
        self._access.require_system(user_id, Permission.USAGE_READ)
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        with self._tx(user_id, workspace_id) as session:
            totals = session.execute(
                text("""
                    select event_type, unit, sum(quantity) quantity
                    from platform.usage_events
                    where workspace_id=:workspace and occurred_at>=:since
                    group by event_type,unit order by event_type,unit
                """),
                {"workspace": workspace_id, "since": since},
            ).mappings().all()
            events = session.execute(
                text("""
                    select id,event_type,quantity,unit,resource_type,resource_id,occurred_at
                    from platform.usage_events
                    where workspace_id=:workspace and occurred_at>=:since
                    order by occurred_at desc,id desc limit :limit offset :offset
                """),
                {"workspace": workspace_id, "since": since, "limit": limit, "offset": offset},
            ).mappings().all()
        return {"window_days": days, "totals": [dict(row) for row in totals],
                "events": [dict(row) for row in events]}

    def governance(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.GOVERNANCE_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(
                text("""
                    select setting_key,enabled,updated_at,updated_by
                    from platform.governance_settings where workspace_id=:workspace
                      and is_active
                    order by setting_key
                """),
                {"workspace": workspace_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def governance_enabled(self, user_id: UUID, workspace_id: UUID, key: str) -> bool:
        with self._tx(user_id, workspace_id) as session:
            value = session.execute(
                text("""
                    select enabled from platform.governance_settings
                    where workspace_id=:workspace and setting_key=:key and is_active
                """),
                {"workspace": workspace_id, "key": key},
            ).scalar_one_or_none()
        return bool(value) if value is not None else False

    def require_governance(self, user_id: UUID, workspace_id: UUID, key: str) -> None:
        if not self.governance_enabled(user_id, workspace_id, key):
            raise GovernanceBlocked(key)

    def update_governance(
        self, user_id: UUID, workspace_id: UUID, key: str, enabled: bool,
        request_id: str | None = None,
    ) -> None:
        self._access.require_system(user_id, Permission.GOVERNANCE_MANAGE)
        with self._tx(user_id, workspace_id) as session:
            changed = session.execute(
                text("""
                    update platform.governance_settings
                    set enabled=:enabled,updated_by=:user,updated_at=now()
                    where workspace_id=:workspace and setting_key=:key and is_active
                """),
                {"enabled": enabled, "user": user_id, "workspace": workspace_id, "key": key},
            )
            if cast(Any, changed).rowcount != 1:
                raise AccessNotFound("governance setting not found")
            self._append_audit(
                session, workspace_id, "governance.updated", "governance_setting",
                None, "succeeded", request_id, {"setting_key": key, "enabled": enabled},
            )

    def audit(
        self, user_id: UUID, workspace_id: UUID, *, action: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.AUDIT_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(
                text("""
                    select id,actor_user_id,action,resource_type,resource_id,
                           outcome,request_id,occurred_at,metadata
                    from platform.audit_events
                    where workspace_id=:workspace
                      and (cast(:action as text) is null or action=cast(:action as text))
                    order by occurred_at desc,id desc limit :limit offset :offset
                """),
                {"workspace": workspace_id, "action": action,
                 "limit": limit, "offset": offset},
            ).mappings().all()
        result: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = _safe_audit_metadata(item.get("metadata") or {})
            result.append(item)
        return result

    def notifications(
        self, user_id: UUID, workspace_id: UUID, *, unread_only: bool = False,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, object]:
        self._access.require(user_id, workspace_id, Permission.NOTIFICATIONS_READ)
        with self._tx(user_id, workspace_id) as session:
            unread = session.execute(
                text("""
                    select count(*) from platform.notifications
                    where workspace_id=:workspace and recipient_user_id=:user
                      and read_at is null
                """),
                {"workspace": workspace_id, "user": user_id},
            ).scalar_one()
            rows = session.execute(
                text("""
                    select id,category,severity,title,message,resource_type,
                           resource_id,created_at,read_at
                    from platform.notifications
                    where workspace_id=:workspace and recipient_user_id=:user
                      and (not :unread_only or read_at is null)
                    order by created_at desc,id desc limit :limit offset :offset
                """),
                {"workspace": workspace_id, "user": user_id,
                 "unread_only": unread_only, "limit": limit, "offset": offset},
            ).mappings().all()
        return {"unread_count": unread, "items": [dict(row) for row in rows]}

    def mark_notifications_read(
        self, user_id: UUID, workspace_id: UUID, notification_id: UUID | None = None,
    ) -> None:
        self._access.require(user_id, workspace_id, Permission.NOTIFICATIONS_READ)
        with self._tx(user_id, workspace_id) as session:
            session.execute(
                text("""
                    update platform.notifications set read_at=coalesce(read_at,now())
                    where workspace_id=:workspace and recipient_user_id=:user
                      and (:notification is null or id=:notification)
                """),
                {"workspace": workspace_id, "user": user_id,
                 "notification": notification_id},
            )

    def operations(
        self, user_id: UUID, workspace_id: UUID, *, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.OPERATIONS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(
                text("""
                    select id,operation_type,status,resource_type,resource_id,
                           started_at,completed_at,safe_error_category
                    from platform.administrative_operations
                    where workspace_id=:workspace
                      and (cast(:status as text) is null or status=cast(:status as text))
                    order by completed_at desc,id desc limit :limit offset :offset
                """),
                {"workspace": workspace_id, "status": status,
                 "limit": limit, "offset": offset},
            ).mappings().all()
        return [dict(row) for row in rows]

    def record_usage(
        self, user_id: UUID, workspace_id: UUID, event_type: str, unit: str,
        *, quantity: int | float = 1, resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None:
        with self._tx(user_id, workspace_id) as session:
            session.execute(
                text("""
                    select platform.record_usage_event(
                      :workspace,:event_type,:quantity,:unit,:resource_type,
                      :resource_id,'{}'::jsonb)
                """),
                {"workspace": workspace_id, "event_type": event_type,
                 "quantity": quantity, "unit": unit,
                 "resource_type": resource_type, "resource_id": resource_id},
            )

    def record_audit(
        self, user_id: UUID, workspace_id: UUID, action: str,
        resource_type: str, resource_id: UUID | None, *, outcome: str = "succeeded",
        request_id: str | None = None, metadata: dict[str, object] | None = None,
    ) -> None:
        with self._tx(user_id, workspace_id) as session:
            self._append_audit(
                session, workspace_id, action, resource_type, resource_id,
                outcome, request_id, metadata,
            )

    def record_operation(
        self, user_id: UUID, workspace_id: UUID, operation_type: str, status: str,
        resource_type: str | None, resource_id: UUID | None, started_at: datetime,
        safe_error_category: str | None = None,
    ) -> None:
        with self._tx(user_id, workspace_id) as session:
            session.execute(
                text("""
                    select platform.record_administrative_operation(
                      :workspace,:operation_type,:status,:resource_type,
                      :resource_id,:started_at,:error_category)
                """),
                {"workspace": workspace_id, "operation_type": operation_type,
                 "status": status, "resource_type": resource_type,
                 "resource_id": resource_id, "started_at": started_at,
                 "error_category": safe_error_category},
            )

    @staticmethod
    def _append_audit(
        session: Session, workspace_id: UUID, action: str, resource_type: str,
        resource_id: UUID | None, outcome: str, request_id: str | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        session.execute(
            text("""
                select platform.append_audit_event(
                  :workspace,:action,:resource_type,:resource_id,:outcome,
                  :request_id,cast(:metadata as jsonb))
            """),
            {"workspace": workspace_id, "action": action,
             "resource_type": resource_type, "resource_id": resource_id,
             "outcome": outcome, "request_id": request_id or "",
             "metadata": json.dumps(metadata or {})},
        )
