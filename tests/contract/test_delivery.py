from fastapi.testclient import TestClient

from knowledge_platform.delivery.app import create_app
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    Evidence,
    GroundedAnswer,
    InsufficientEvidence,
    PolicyDenied,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId


class FakeService:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    def ask(self, *, question: str) -> object:
        return self.outcome


def test_health_and_demo_page() -> None:
    client = TestClient(create_app(FakeService(InsufficientEvidence("no evidence"))))
    assert client.get("/health").json()["status"] == "ok"
    page = client.get("/").text
    assert "Yemen History Assistant" in page
    assert "/api/demo/ask" in page
    assert 'lang="ar"' in page
    assert 'dir="rtl"' in page
    assert "الأدلة والمصادر" in page
    assert "provenance_locator" in page
    assert "textContent=JSON.stringify" not in page
    assert "render(await response.json())" in page
    assert "node.dir='auto'" in page
    assert "node.dir='ltr'" in page


def test_typed_grounded_response_preserves_evidence() -> None:
    outcome = GroundedAnswer("answer", (Evidence(KnowledgeSourceId.new(), "fact", "fixture#1"),))
    response = TestClient(create_app(FakeService(outcome))).post(
        "/api/demo/ask", json={"question": "question"}
    )
    assert response.json()["outcome"] == "GroundedAnswer"
    assert response.json()["evidence"][0]["provenance_locator"] == "fixture#1"


def test_insufficient_and_policy_denied_outcomes_are_typed() -> None:
    for outcome, expected in (
        (InsufficientEvidence("no evidence"), "InsufficientEvidence"),
        (PolicyDenied("denied"), "PolicyDenied"),
    ):
        response = TestClient(create_app(FakeService(outcome))).post(
            "/api/demo/ask", json={"question": "question"}
        )
        assert response.json()["outcome"] == expected


def test_unexpected_failure_does_not_leak_details() -> None:
    class Failing:
        def ask(self, *, question: str) -> object:
            raise RuntimeError("password=do-not-leak DSN=secret")

    response = TestClient(create_app(Failing())).post(
        "/api/demo/ask", json={"question": "question"}
    )
    assert response.status_code == 500
    assert response.json() == {
        "outcome": "TechnicalFailure",
        "reason": "request could not be completed",
    }


def test_default_demo_requests_have_isolated_vector_state() -> None:
    client = TestClient(create_app())

    first = client.post("/api/demo/ask", json={"question": "What is Sana'a history?"})
    assert first.json()["outcome"] == "GroundedAnswer"
    assert first.json()["evidence"][0]["source_id"]
    assert first.json()["evidence"][0]["content"]
    assert first.json()["evidence"][0]["provenance_locator"] == "yemen-demo#1"

    second = client.post("/api/demo/ask", json={"question": "unsupported"})
    assert second.json()["outcome"] == "InsufficientEvidence"

    third = client.post("/api/demo/ask", json={"question": "What is Sana'a history?"})
    assert third.json()["outcome"] == "GroundedAnswer"
    assert third.json()["evidence"][0]["provenance_locator"] == "yemen-demo#1"
