"""Stage 7B workspace administrative APIs."""

from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from knowledge_platform.application.administration import AdministrationPort


class GovernanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


def create_administration_router(service: AdministrationPort, *, system: bool = False) -> APIRouter:
    prefix = "/api/system/workspaces/{workspace_id}" if system else "/api/workspaces/{workspace_id}"
    router = APIRouter(prefix=prefix)

    def user(request: Request) -> UUID:
        return request.state.user.id

    @router.get("/usage")
    def usage(
        workspace_id: UUID, request: Request, days: int = Query(30, ge=1, le=365),
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        return service.usage(user(request), workspace_id, days=days, limit=limit, offset=offset)

    @router.get("/governance")
    def governance(workspace_id: UUID, request: Request) -> list[dict[str, object]]:
        return service.governance(user(request), workspace_id)

    @router.patch("/governance/{setting_key}", status_code=204)
    def update_governance(
        workspace_id: UUID, setting_key: str, payload: GovernanceUpdate, request: Request,
    ) -> None:
        service.update_governance(
            user(request), workspace_id, setting_key, payload.enabled,
            request.headers.get("x-request-id"),
        )

    @router.get("/audit")
    def audit(
        workspace_id: UUID, request: Request, action: str | None = None,
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    ) -> list[dict[str, object]]:
        return service.audit(
            user(request), workspace_id, action=action, limit=limit, offset=offset,
        )

    @router.get("/notifications")
    def notifications(
        workspace_id: UUID, request: Request, unread_only: bool = False,
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        return service.notifications(
            user(request), workspace_id, unread_only=unread_only,
            limit=limit, offset=offset,
        )

    @router.patch("/notifications/read", status_code=204)
    def mark_all_read(workspace_id: UUID, request: Request) -> None:
        service.mark_notifications_read(user(request), workspace_id)

    @router.patch("/notifications/{notification_id}/read", status_code=204)
    def mark_read(workspace_id: UUID, notification_id: UUID, request: Request) -> None:
        service.mark_notifications_read(user(request), workspace_id, notification_id)

    @router.get("/administrative-operations")
    def operations(
        workspace_id: UUID, request: Request, status: str | None = Query(None),
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    ) -> list[dict[str, object]]:
        return service.operations(
            user(request), workspace_id, status=status, limit=limit, offset=offset,
        )

    return router
