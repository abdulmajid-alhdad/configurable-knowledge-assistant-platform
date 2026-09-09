"""Contracts for the current buildless Workspace SPA."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_product_shell_is_buildless_arabic_rtl_and_deep_linkable() -> None:
    index = read("frontend/index.html")
    bootstrap = read("frontend/shared/bootstrap.js")
    routes = read("frontend/app/routes.js")
    assert 'lang="ar" dir="rtl"' in index
    assert "StaticFiles" not in bootstrap
    for route in ("/app", "/app/assistants", "/app/knowledge", "/app/conversations"):
        assert route in routes
    assert "import(asset(`/assets/${surface}/entry.js`))" in bootstrap


def test_product_page_uses_generic_workspace_api_contracts() -> None:
    page = read("frontend/app/pages.js")
    for endpoint in (
        "/api/me/workspaces",
        "/api/workspaces/${state.workspaceId}/assistants",
        "/api/workspaces/${state.workspaceId}/sources",
        "/api/workspaces/${state.workspaceId}/conversations",
        "/conversations/${id}/ask",
    ):
        assert endpoint in page
    assert "/api/demo/ask" not in page
    assert "supabase" not in page.lower()


def test_product_page_renders_and_updates_assistant_knowledge_scope() -> None:
    page = read("frontend/app/pages.js")
    assert "source.artifact" in page
    assert "knowledge.create" in page
    assert "state.permissions.has(\"knowledge.create\")" in page
    assert "source_ids" not in page
    assert "Object.hasOwn" in page


def test_product_page_upload_and_reprocess_are_distinct() -> None:
    page = read("frontend/app/pages.js")
    assert '"x-file-name": encodeURIComponent(selectedFile.name)' in page
    assert "body: selectedFile" in page
    assert "/process" in page
    assert "إعادة معالجة المصدر" in page


def test_product_page_has_typed_outcome_and_evidence_rendering() -> None:
    page = read("frontend/app/pages.js")
    for outcome in ("GroundedAnswer", "InsufficientEvidence", "PolicyDenied", "TechnicalFailure"):
        assert outcome in page
    assert "evidence || []" in page
    assert "dir: \"auto\"" in page
    assert "innerHTML" not in page
    assert "JSON.stringify(o)" not in page


def test_product_page_only_persists_workspace_selection() -> None:
    page = read("frontend/app/pages.js")
    assert 'localStorage.getItem("selected_workspace_id")' in page
    assert 'localStorage.setItem("selected_workspace_id"' not in page
    assert "DATABASE_URL" not in page
    assert "OPENROUTER" not in page


def test_product_page_maps_source_labels_to_backend_kinds() -> None:
    page = read("frontend/app/pages.js")
    assert 'value: "document"' in page
    assert 'value: "structured"' in page
    assert 'value: "file"' not in page
    assert 'value: "url"' not in page
    assert 'kind: kind.value' in page
