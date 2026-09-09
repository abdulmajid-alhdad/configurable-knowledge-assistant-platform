"""Central authentication and permission enforcement for the Control Plane."""

import logging
import re
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from knowledge_platform.application.access_control import (
    AccessControlPort,
    AccessDenied,
    AccessNotFound,
)
from knowledge_platform.application.security_context import bind_user, reset_user
from knowledge_platform.infrastructure.auth.supabase import (
    AuthProviderFailure,
    AuthSession,
    SupabaseAuthAdapter,
)
from knowledge_platform.modules.access_control.domain import (
    AuthenticatedUser,
    Permission,
    PermissionScope,
    permission_definition,
)

logger = logging.getLogger(__name__)
ACCESS_COOKIE = "kp_access"
REFRESH_COOKIE = "kp_refresh"
UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
PUBLIC = (
    "/health",
    "/ready",
    "/login",
    "/app/invitations/accept",
    "/api/auth/sign-in",
    "/api/auth/invitations/activation/preview",
    "/api/auth/invitations/activation",
)

RULES: tuple[tuple[re.Pattern[str], dict[str, Permission]], ...] = (
    (
        re.compile(r"^/api/workspaces/[^/]+/assistants(?:/|$)"),
        {
            "GET": Permission.ASSISTANT_READ,
            "POST": Permission.ASSISTANT_CREATE,
            "PATCH": Permission.ASSISTANT_UPDATE,
        },
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/sources/[^/]+/(?:upload)$"),
        {"POST": Permission.KNOWLEDGE_CREATE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/sources/[^/]+/(?:process)$"),
        {"POST": Permission.KNOWLEDGE_PROCESS},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/sources(?:/|$)"),
        {"GET": Permission.KNOWLEDGE_READ, "POST": Permission.KNOWLEDGE_CREATE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/conversations/[^/]+/title$"),
        {"PATCH": Permission.CONVERSATIONS_RENAME},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/conversations/[^/]+/archive$"),
        {"PATCH": Permission.CONVERSATIONS_ARCHIVE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/conversations(?:/|$)"),
        {"GET": Permission.CONVERSATIONS_READ, "POST": Permission.CONVERSATIONS_CREATE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/evaluation/suites(?:/|$)"),
        {"GET": Permission.EVALUATION_READ},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/evaluation/runs(?:/|$)"),
        {"GET": Permission.EVALUATION_READ, "POST": Permission.EVALUATION_RUN},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/members(?:/|$)"),
        {
            "GET": Permission.MEMBERS_READ,
            "PATCH": Permission.MEMBERS_MANAGE,
            "DELETE": Permission.MEMBERS_MANAGE,
        },
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/teams(?:/|$)"),
        {
            "GET": Permission.TEAMS_READ,
            "POST": Permission.TEAMS_MANAGE,
            "PUT": Permission.TEAMS_MANAGE,
            "PATCH": Permission.TEAMS_MANAGE,
            "DELETE": Permission.TEAMS_MANAGE,
        },
    ),
    (re.compile(r"^/api/workspaces/[^/]+/permissions$"), {"GET": Permission.ROLES_READ}),
    (
        re.compile(r"^/api/workspaces/[^/]+/roles(?:/|$)"),
        {
            "GET": Permission.ROLES_READ,
            "POST": Permission.ROLES_MANAGE,
            "PATCH": Permission.ROLES_MANAGE,
            "DELETE": Permission.ROLES_MANAGE,
        },
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/invitations(?:/|$)"),
        {
            "GET": Permission.INVITATIONS_READ,
            "POST": Permission.INVITATIONS_MANAGE,
            "DELETE": Permission.INVITATIONS_MANAGE,
        },
    ),
    (re.compile(r"^/api/workspaces/[^/]+/usage$"), {"GET": Permission.USAGE_READ}),
    (
        re.compile(r"^/api/workspaces/[^/]+/governance(?:/|$)"),
        {"GET": Permission.GOVERNANCE_READ, "PATCH": Permission.GOVERNANCE_MANAGE},
    ),
    (re.compile(r"^/api/workspaces/[^/]+/audit$"), {"GET": Permission.AUDIT_READ}),
    (
        re.compile(r"^/api/workspaces/[^/]+/notifications(?:/|$)"),
        {"GET": Permission.NOTIFICATIONS_READ, "PATCH": Permission.NOTIFICATIONS_READ},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/administrative-operations$"),
        {"GET": Permission.OPERATIONS_READ},
    ),
    (re.compile(r"^/api/workspaces/[^/]+/plans$"), {"GET": Permission.PLANS_READ}),
    (
        re.compile(r"^/api/workspaces/[^/]+/subscription$"),
        {
            "GET": Permission.SUBSCRIPTIONS_READ,
            "PATCH": Permission.SUBSCRIPTIONS_MANAGE,
        },
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/entitlements$"),
        {"GET": Permission.SUBSCRIPTIONS_READ},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/providers(?:/|$)"),
        {"GET": Permission.PROVIDERS_READ, "PATCH": Permission.PROVIDERS_MANAGE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/credentials(?:/|$)"),
        {
            "GET": Permission.CREDENTIALS_READ,
            "POST": Permission.CREDENTIALS_MANAGE,
            "DELETE": Permission.CREDENTIALS_MANAGE,
        },
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/security$"),
        {"GET": Permission.SECURITY_READ, "PATCH": Permission.SECURITY_MANAGE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/settings$"),
        {
            "GET": Permission.SETTINGS_READ,
            "PATCH": Permission.WORKSPACE_SETTINGS_MANAGE,
        },
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/api-keys$"),
        {"GET": Permission.API_KEYS_READ, "POST": Permission.API_KEYS_MANAGE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+/api-keys/[^/]+$"),
        {"DELETE": Permission.API_KEYS_MANAGE},
    ),
    (
        re.compile(r"^/api/workspaces/[^/]+$"),
        {"GET": Permission.WORKSPACE_READ, "PATCH": Permission.WORKSPACE_MANAGE},
    ),
)


def permission_for(path: str, method: str) -> Permission | None:
    if path.startswith("/api/system/"):
        if path == "/api/system/identity/provision" and method == "POST":
            return Permission.INVITATIONS_MANAGE
        system_path = path.replace("/api/system", "/api", 1)
        if path == "/api/system/usage/provider":
            return Permission.USAGE_READ
        if path == "/api/system/providers/runtime" and method == "GET":
            return Permission.PROVIDERS_READ
        if re.match(r"^/api/system/providers/runtime/(generation|embedding)$", path):
            return (
                Permission.PROVIDERS_READ
                if method == "GET"
                else Permission.PROVIDERS_MANAGE
            )
        if re.match(r"^/api/system/conversations(?:/|$)", path):
            if method == "GET":
                return Permission.SYSTEM_CONVERSATIONS_READ
            if method == "POST":
                return Permission.SYSTEM_CONVERSATIONS_CREATE
            if path.endswith("/title") and method == "PATCH":
                return Permission.SYSTEM_CONVERSATIONS_RENAME
            if path.endswith("/archive") and method == "PATCH":
                return Permission.SYSTEM_CONVERSATIONS_ARCHIVE
            return None
        if path == "/api/system/users" and method == "GET":
            return Permission.SYSTEM_ACCESS_READ
        if re.match(r"^/api/system/access(?:/|$)", path):
            return (
                Permission.SYSTEM_ACCESS_READ
                if method == "GET"
                else Permission.SYSTEM_ACCESS_MANAGE
            )
        if system_path in {"/api/roles", "/api/permissions"}:
            return Permission.ROLES_READ
        if system_path == "/api/workspaces" and method == "POST":
            return Permission.WORKSPACE_MANAGE
        if re.match(r"^/api/workspaces/[^/]+/assistants(?:/|$)", system_path):
            if method == "GET":
                return Permission.SYSTEM_ASSISTANTS_READ
            if method == "POST":
                return Permission.ASSISTANT_CREATE
            if method == "PATCH":
                return Permission.ASSISTANT_UPDATE
        if re.match(r"^/api/workspaces/[^/]+/sources(?:/|$)", system_path):
            if "/assistants/" in system_path and "/sources/" in system_path:
                return (
                    Permission.KNOWLEDGE_ATTACH
                    if method in UNSAFE
                    else Permission.SYSTEM_KNOWLEDGE_READ
                )
            if system_path.endswith("/process"):
                return Permission.SYSTEM_KNOWLEDGE_PROCESS
            if method == "GET":
                return Permission.SYSTEM_KNOWLEDGE_READ
            return Permission.SYSTEM_KNOWLEDGE_CREATE
        if re.match(r"^/api/workspaces/[^/]+/members(?:/|$)", system_path):
            return (
                Permission.SYSTEM_MEMBERSHIPS_READ
                if method == "GET"
                else Permission.MEMBERS_MANAGE
            )
        if re.match(r"^/api/workspaces/[^/]+/teams(?:/|$)", system_path):
            return Permission.TEAMS_READ if method == "GET" else Permission.TEAMS_MANAGE
        if system_path.endswith("/permissions") or re.match(
            r"^/api/workspaces/[^/]+/roles", system_path
        ):
            return Permission.ROLES_READ if method == "GET" else Permission.ROLES_MANAGE
        if re.match(r"^/api/workspaces/[^/]+/invitations(?:/|$)", system_path):
            return Permission.INVITATIONS_READ if method == "GET" else Permission.INVITATIONS_MANAGE
        if system_path == "/api/workspaces" or re.match(r"^/api/workspaces/[^/]+$", system_path):
            return (
                Permission.SYSTEM_WORKSPACES_READ
                if method == "GET"
                else Permission.WORKSPACE_MANAGE
            )
        # The remaining System administration routes retain their canonical
        # permission mapping while gaining an explicit /api/system boundary.
        return permission_for(system_path, method)
    if path == "/api/workspaces" and method == "POST":
        return Permission.WORKSPACE_MANAGE
    if "/assistants/" in path and "/sources" in path and method == "GET":
        return Permission.KNOWLEDGE_READ
    if re.match(r"^/api/workspaces/[^/]+/assistants/[^/]+/conversations$", path):
        return Permission.CONVERSATIONS_CREATE
    if "/assistants/" in path and "/sources/" in path and method in UNSAFE:
        return Permission.KNOWLEDGE_ATTACH
    if path.endswith("/ask"):
        return Permission.CONVERSATIONS_CREATE
    for pattern, methods in RULES:
        if pattern.match(path):
            return methods.get(method)
    return None


def _workspace_admin_mutation(path: str, method: str) -> bool:
    if method not in UNSAFE or not path.startswith("/api/workspaces"):
        return False
    if method == "POST" and (
        re.fullmatch(r"/api/workspaces/[^/]+/sources", path)
        or re.fullmatch(
            r"/api/workspaces/[^/]+/sources/[^/]+/(?:upload|process)", path
        )
    ):
        return False
    if path == "/api/workspaces":
        return True
    if re.match(r"^/api/workspaces/[^/]+$", path):
        return True
    blocked = (
        "/assistants", "/sources", "/members", "/teams", "/roles",
        "/permissions", "/invitations", "/governance", "/providers",
        "/credentials", "/security", "/settings", "/subscription", "/api-keys",
    )
    return (
        any(segment in path for segment in blocked)
        and "/conversations" not in path
        and "/evaluation/" not in path
    )


def _workspace_system_surface(path: str) -> bool:
    if not path.startswith("/api/workspaces/"):
        return False
    system_segments = (
        "/teams", "/roles", "/permissions", "/invitations", "/governance",
        "/usage", "/audit", "/notifications", "/administrative-operations",
        "/plans", "/subscription", "/entitlements", "/providers", "/credentials",
        "/security", "/settings", "/api-keys",
    )
    return any(segment in path for segment in system_segments)


def set_session_cookies(response: Response, session: AuthSession, secure: bool) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=max(60, session.expires_in),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, secure: bool) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")


class ControlPlaneSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        auth: SupabaseAuthAdapter,
        access: AccessControlPort,
        cookie_secure: bool,
    ) -> None:
        super().__init__(app)
        self.auth, self.access, self.cookie_secure = auth, access, cookie_secure

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if (
            path in PUBLIC
            or path.startswith("/assets/")
            or path.startswith("/docs")
            or path.startswith("/openapi")
        ):
            return await call_next(request)
        user: AuthenticatedUser | None = None
        refreshed: AuthSession | None = None
        refresh_attempted = False
        access_token = request.cookies.get(ACCESS_COOKIE)
        try:
            if access_token:
                user = self.auth.get_user(access_token)
            elif request.cookies.get(REFRESH_COOKIE):
                refresh_attempted = True
                refreshed = self.auth.refresh(request.cookies[REFRESH_COOKIE])
                user = refreshed.user
        except AuthProviderFailure as error:
            logger.info("session_validation_failed", extra={"category": error.category})
            refresh = request.cookies.get(REFRESH_COOKIE)
            if refresh and refreshed is None and not refresh_attempted:
                try:
                    refreshed = self.auth.refresh(refresh)
                    user = refreshed.user
                except AuthProviderFailure as refresh_error:
                    logger.info(
                        "session_refresh_failed", extra={"category": refresh_error.category}
                    )
        if user is None:
            response: Response = (
                RedirectResponse("/login", status_code=303)
                if path.startswith(("/app", "/system"))
                else JSONResponse({"detail": "authentication required"}, 401)
            )
            clear_session_cookies(response, self.cookie_secure)
            return response
        if request.method in UNSAFE:
            origin = request.headers.get("origin")
            same_origin_fetch = request.headers.get("sec-fetch-site") == "same-origin"
            if origin != str(request.base_url).rstrip("/") and not same_origin_fetch:
                return JSONResponse({"detail": "request origin rejected"}, 403)
        token = bind_user(user.id)
        try:
            request.state.user = user
            if _workspace_system_surface(path):
                return JSONResponse(
                    {"detail": "administrative operation requires system authority"}, 403
                )
            if _workspace_admin_mutation(path, request.method):
                return JSONResponse(
                    {"detail": "administrative operation requires system authority"}, 403
                )
            match = re.match(r"^/api/workspaces/([0-9a-fA-F-]{36})(?:/|$)", path)
            if match is None:
                match = re.match(r"^/api/system/workspaces/([0-9a-fA-F-]{36})(?:/|$)", path)
            required = permission_for(path, request.method)
            if match and required is None:
                return JSONResponse({"detail": "workspace operation is not authorized"}, 403)
            if required:
                try:
                    definition = permission_definition(required)
                    if definition.scope is PermissionScope.SYSTEM:
                        self.access.require_system(user.id, required)
                    elif match:
                        self.access.require(user.id, UUID(match.group(1)), required)
                    else:
                        return JSONResponse(
                            {"detail": "workspace scope is required"}, 403
                        )
                except AccessNotFound:
                    return JSONResponse({"detail": "resource not found"}, 404)
                except AccessDenied:
                    logger.info("permission_denied", extra={"permission": required.value})
                    return JSONResponse({"detail": "permission denied"}, 403)
            response = await call_next(request)
            response.headers["cache-control"] = "private, no-store"
            if refreshed:
                set_session_cookies(response, refreshed, self.cookie_secure)
            return response
        finally:
            reset_user(token)
