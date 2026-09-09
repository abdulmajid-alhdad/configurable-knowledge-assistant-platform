"""Contract coverage for the generic product web shell."""

from collections.abc import Callable
from typing import cast

from knowledge_platform.delivery.app import create_app


def _page() -> str:
    route = next(
        route for route in create_app().routes if getattr(route, "path", None) == "/app/acceptance"
    )
    return cast(Callable[[], str], route.endpoint)()


def test_product_page_declares_product_sections_and_rtl() -> None:
    page = _page()
    assert '<html lang="ar" dir="rtl">' in page
    for text in ("المساعد المعرفي", "مساحة العمل", "المساعد", "مصادر المعرفة", "محادثة جديدة"):
        assert text in page


def test_product_page_uses_generic_management_and_conversation_contracts() -> None:
    page = _page()
    for endpoint in (
        "/api/workspaces",
        "/api/workspaces/'+wid+'/assistants",
        "/api/workspaces/'+wid+'/sources",
        "/upload",
        "/process",
        "/assistants/'+aid+'/conversations",
        "/conversations/'+cid+'/ask",
        "/assistants/'+aid+'/sources",
        "/assistants/'+aid+'/sources/'+s.id",
    ):
        assert endpoint in page
    assert "/api/demo/ask" not in page
    assert "source_ids" not in page
    assert "FormData" not in page


def test_product_page_renders_and_updates_assistant_knowledge_scope() -> None:
    page = _page()
    assert "async function loadScope()" in page
    assert "renderScope(attached)" in page
    assert "$('assistants').onchange" in page
    assert "availableSources" in page
    assert "إضافة إلى نطاق المساعد" in page
    assert "إزالة من نطاق المساعد" in page
    assert "اختر مساعدًا لعرض نطاق المعرفة." in page
    assert "لا توجد مصادر معرفة في مساحة العمل." in page
    assert "method:isAttached?'DELETE':'POST'" in page
    assert (
        "body:"
        not in page[page.index("method:isAttached?") : page.index("method:isAttached?") + 100]
    )


def test_product_page_upload_and_reprocess_are_distinct() -> None:
    page = _page()
    assert "'x-file-name':f.name" in page
    assert "body:f" in page
    assert "body:JSON.stringify({question:$('question').value})" in page
    assert "إعادة المعالجة تستخدم الملف المحفوظ" in page


def test_product_page_has_typed_outcome_and_evidence_rendering() -> None:
    page = _page()
    for outcome in ("GroundedAnswer", "InsufficientEvidence", "PolicyDenied"):
        assert outcome in page
    # Technical failures use the safe generic fallback branch for non-grounded outcomes.
    assert "if(o.outcome!=='GroundedAnswer'&&!o.answer)" in page
    assert "p.textContent=o.reason" not in page
    assert "o.evidence||[]" in page
    assert "p.dir='auto'" in page
    assert "m.dir='ltr'" in page
    assert "aria-live" in page
    assert "JSON.stringify(o)" not in page


def test_product_page_only_persists_navigation_state() -> None:
    page = _page()
    assert "localStorage.setItem('workspace_id',wid)" in page
    assert "localStorage.setItem('api" not in page
    assert "DATABASE_URL" not in page
    assert "OPENROUTER" not in page
    assert "KNOWLEDGE_ARTIFACT_ROOT" not in page


def test_product_page_maps_source_labels_to_backend_kinds() -> None:
    page = _page()
    assert '<option value="document">' in page
    assert '<option value="structured">' in page
    assert '<option value="file">' not in page
    assert '<option value="url">' not in page
    assert "'/api/workspaces/'+wid+'/sources'" in page
    assert "kind:$('sourceKind').value" in page
