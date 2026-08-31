"""Contract coverage for the generic product web shell."""

from collections.abc import Callable
from typing import cast

from knowledge_platform.delivery.app import create_app


def _page() -> str:
    route = next(route for route in create_app().routes if getattr(route, "path", None) == "/app")
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
    ):
        assert endpoint in page
    assert "/api/demo/ask" not in page
    assert "source_ids" not in page
    assert "FormData" not in page


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
    # Technical failures use the safe generic fallback branch for any non-grounded outcome.
    assert "حدث خطأ آمن أثناء معالجة السؤال" in page
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
