from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_authenticated_shells_expose_identity_and_logout_boundary() -> None:
    shell = read("frontend/shared/shell.js")
    session = read("frontend/shared/session.js")
    surface = read("frontend/shared/surface.js")
    css = read("frontend/styles/foundation.css")

    assert "تسجيل الخروج" in shell
    assert "logoutCurrentBrowser" in shell
    assert 'getJSON("/api/me")' in surface
    assert 'request("/api/auth/sign-out", { method: "POST" })' in session
    assert "workspaceCache.clear()" in session
    assert "clearInflight()" in session
    assert 'window.location.replace("/login")' in session
    assert "sidebar-footer-context" in css
    assert "sidebar-footer-identity" in css
    assert "sidebar-footer-logout" in css
    assert "account-menu" not in css
    assert "account-email" not in shell


def test_system_shell_fails_closed_without_system_permissions() -> None:
    entry = read("frontend/system/entry.js")

    assert 'getJSON("/api/system/me/permissions")' in entry
    assert "!window.__controlPlanePermissions.length" in entry
    assert 'window.location.replace("/app")' in entry
    assert 'return startSurface("system", SYSTEM_ROUTES)' in entry


def test_footer_uses_workspace_name_and_non_email_identity_sources() -> None:
    shell = read("frontend/shared/shell.js")
    pages = read("frontend/app/pages.js")

    assert 'surface === "system" ? "إدارة النظام"' in shell
    assert '"مساحة العمل:"' in shell
    assert '"المستخدم:"' in shell
    assert '"جارٍ تحديد النطاق…"' in shell
    assert 'identity?.display_name || identity?.username || identity?.name' in shell
    assert "identity?.email" not in shell
    assert "identity?.id" not in shell
    assert "sidebar-footer-label" in shell
    assert "sidebar-footer-value" in shell
    assert "grid-template-columns: max-content minmax(0, 1fr)" in read(
        "frontend/styles/foundation.css"
    )
    assert "setCurrentWorkspaceName(current.name)" in pages


def test_frontend_footer_revision_reloads_the_authenticated_module_graph() -> None:
    index = read("frontend/index.html")
    bootstrap = read("frontend/shared/bootstrap.js")
    surface = read("frontend/shared/surface.js")
    shell = read("frontend/shared/shell.js")

    revision = "stage4-auth-footer-2"
    assert revision in index
    assert revision in bootstrap
    assert f"shell.js?v={revision}" in surface
    assert f"session.js?v={revision}" in shell
