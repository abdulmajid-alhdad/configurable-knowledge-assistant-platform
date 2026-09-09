"""Same-origin authentication delivery; tokens remain HttpOnly."""
# ruff: noqa: E501

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.delivery.security import (
    ACCESS_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from knowledge_platform.infrastructure.auth.supabase import AuthProviderFailure, SupabaseAuthAdapter

logger = logging.getLogger(__name__)
LOGIN_HTML = """<!doctype html><html lang=\"ar\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>تسجيل الدخول</title><style>body{margin:0;background:#f5f6f8;color:#20242b;font:13px system-ui;display:grid;place-items:center;min-height:100vh}.box{width:min(360px,calc(100vw - 24px));background:#fff;border:1px solid #dfe2e6;border-radius:8px;padding:18px}h1{font-size:19px;margin:0 0 14px}label{display:block;margin:9px 0 4px}input,button{box-sizing:border-box;width:100%;height:34px;border:1px solid #c9ced5;border-radius:6px;padding:6px 9px;font:inherit}button{margin-top:12px;background:#176b87;color:#fff;border:0;font-weight:700}.error{color:#a33;margin-top:9px}</style></head><body><form class=\"box\" id=\"login\"><h1>تسجيل الدخول إلى منصة المعرفة</h1><label for=\"email\">البريد الإلكتروني</label><input id=\"email\" type=\"email\" autocomplete=\"username\" required><label for=\"password\">كلمة المرور</label><input id=\"password\" type=\"password\" autocomplete=\"current-password\" required><button>تسجيل الدخول</button><p id=\"error\" class=\"error\" aria-live=\"polite\"></p></form><script>document.querySelector('#login').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;const r=await fetch('/api/auth/sign-in',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:email.value,password:password.value})});if(r.ok){const result=await r.json();location.replace(result.redirect_to)}else{document.querySelector('#error').textContent='تعذر تسجيل الدخول. تحقق من البيانات وحاول مرة أخرى.';b.disabled=false}}</script></body></html>"""


class SignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


def authenticated_destination(access: AccessControlPort, user_id: UUID) -> str:
    """Select the default surface without conflating SYSTEM and WORKSPACE scope."""
    if access.system_permissions(user_id):
        return "/system"
    if access.discover_workspaces(user_id):
        return "/app"
    # Preserve the existing no-access behavior; /app renders the no-Workspace state.
    return "/app"


def create_auth_router(
    auth: SupabaseAuthAdapter, access: AccessControlPort, *, secure: bool
) -> APIRouter:
    router = APIRouter()

    @router.get("/login", response_class=HTMLResponse)
    def login(request: Request) -> Response:
        access_token = request.cookies.get(ACCESS_COOKIE)
        if access_token:
            try:
                current_user = auth.get_user(access_token)
                destination = authenticated_destination(access, current_user.id)
                return RedirectResponse(destination, status_code=303)
            except AuthProviderFailure:
                pass
        return HTMLResponse(LOGIN_HTML)

    @router.post("/api/auth/sign-in")
    def sign_in(payload: SignIn, request: Request) -> JSONResponse:
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "request origin rejected")
        try:
            session = auth.sign_in(email=payload.email, password=payload.password)
            access.sync_profile(session.user)
            destination = authenticated_destination(access, session.user.id)
        except AuthProviderFailure as error:
            logger.info("login_failed", extra={"category": error.category})
            raise HTTPException(401, "sign in failed") from None
        response = JSONResponse(
            {
                "user": {
                    "id": str(session.user.id),
                    "email": session.user.email,
                    "display_name": session.user.display_name,
                },
                "redirect_to": destination,
            }
        )
        set_session_cookies(response, session, secure)
        return response

    @router.post("/api/auth/sign-out", status_code=204)
    def sign_out(request: Request) -> JSONResponse:
        token = request.cookies.get(ACCESS_COOKIE)
        if token:
            try:
                auth.sign_out(token)
            except AuthProviderFailure as error:
                logger.info("logout_provider_failed", extra={"category": error.category})
        response = JSONResponse(content=None, status_code=204)
        clear_session_cookies(response, secure)
        return response

    @router.get("/api/me")
    def me(request: Request) -> dict[str, object]:
        user = request.state.user
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "status": "active",
        }

    return router
