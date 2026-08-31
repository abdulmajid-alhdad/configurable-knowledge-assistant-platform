"""Contracts for the small operational/evaluation surface."""
from fastapi.testclient import TestClient

from knowledge_platform.delivery.app import create_app


def test_product_page_mentions_operational_evaluation_surface() -> None:
    page = next(r.endpoint() for r in create_app().routes if getattr(r, "path", None) == "/app")
    assert "التقييم والتشغيل" in page
    assert "/health" in page
    assert "/ready" in page
    assert "/api/evaluation/suites" in page


def test_health_is_liveness_without_runtime() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
