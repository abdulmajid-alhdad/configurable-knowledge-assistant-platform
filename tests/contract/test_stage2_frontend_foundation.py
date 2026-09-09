import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from knowledge_platform.delivery.app import create_app

ROOT = Path(__file__).parents[2]


def _get(path: str) -> tuple[int, dict[str, str], bytes]:
    application = create_app()
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("test", 1234),
        "server": ("test", 80),
        "root_path": "",
    }
    asgi = application
    callable_app: Callable[
        [
            dict[str, Any],
            Callable[[], Awaitable[dict[str, Any]]],
            Callable[[dict[str, Any]], Awaitable[None]],
        ],
        Awaitable[None],
    ] = asgi
    asyncio.run(callable_app(scope, receive, send))

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return start["status"], headers, body


def test_workspace_and_system_frontend_routes_serve_the_rtl_entrypoint() -> None:
    for route in (
        "/app",
        "/app/test-deep-link",
        "/system",
        "/system/test-deep-link",
    ):
        status, _headers, body = _get(route)
        text = body.decode("utf-8")
        assert status == 200
        assert 'lang="ar" dir="rtl"' in text
        assert "/assets/shared/bootstrap.js" in text


def test_api_paths_never_fall_back_to_the_frontend_entrypoint() -> None:
    status, headers, _body = _get("/api/unknown-route")

    assert status == 404
    assert headers["content-type"].startswith("application/json")


def test_health_and_readiness_contracts_are_unchanged() -> None:
    health_status, _health_headers, health_body = _get("/health")
    ready_status, _ready_headers, ready_body = _get("/ready")

    assert health_status == 200
    assert health_body == b'{"status":"ok","service":"knowledge-platform"}'
    assert ready_status == 200
    assert ready_body == b'{"status":"ready","mode":"demo"}'


def test_frontend_asset_is_served() -> None:
    status, headers, body = _get("/assets/styles/foundation.css")

    assert status == 200
    assert headers["content-type"].startswith("text/css")
    assert b".control-shell" in body


def test_spa_foundation_has_separate_route_spaces_and_data_only_cache_contract() -> None:
    router = (ROOT / "frontend/shared/router.js").read_text(encoding="utf-8")
    cache = (ROOT / "frontend/shared/cache.js").read_text(encoding="utf-8")
    dom = (ROOT / "frontend/shared/dom.js").read_text(encoding="utf-8")
    app_routes = (ROOT / "frontend/app/routes.js").read_text(encoding="utf-8")
    system_routes = (ROOT / "frontend/system/routes.js").read_text(encoding="utf-8")

    assert "history.pushState" in router
    assert "popstate" in router
    assert "routeSpace" in router
    assert "workspaceKey" in cache
    assert "staleWhileRevalidate" in cache
    assert "containsDom" in cache
    assert "innerHTML" not in dom
    assert '"/app/conversations"' in app_routes
    assert '"/system/access"' in system_routes
