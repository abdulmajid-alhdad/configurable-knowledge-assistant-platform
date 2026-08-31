"""Contracts for the small operational/evaluation surface."""
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_platform.delivery.app import create_app
from knowledge_platform.infrastructure.evaluation.catalog import FilesystemSuiteCatalog
from knowledge_platform.infrastructure.evaluation.suites import load_suite


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


def test_readiness_is_safe_and_distinct_from_health() -> None:
    client = TestClient(create_app())
    health = client.get("/health").json()
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json() != health
    assert not any(
        secret in ready.text
        for secret in ("DATABASE_URL", "OPENROUTER", "KNOWLEDGE_ARTIFACT_ROOT")
    )


def test_suite_catalog_lists_trusted_artifacts_with_canonical_hashes() -> None:
    root = Path("evaluation/suites")
    summaries = FilesystemSuiteCatalog(root).list_summaries()
    assert summaries
    for summary in summaries:
        artifact = load_suite(root / f"{summary.key}.json")
        assert summary.key == artifact.suite.key
        assert summary.version == artifact.suite.version
        assert summary.case_count == len(artifact.suite.cases)
        assert summary.sha256 == artifact.sha256


def test_product_surface_does_not_claim_unsupported_run_execution_or_history() -> None:
    page = next(
        r.endpoint() for r in create_app().routes if getattr(r, "path", None) == "/app"
    )
    assert "/api/evaluation/suites" in page
    assert "/evaluation/runs" not in page
    assert "تشغيل التقييم" not in page
    assert "JSON.stringify(o)" not in page
    assert "accuracy" not in page.lower()
    assert "faithfulness" not in page.lower()
