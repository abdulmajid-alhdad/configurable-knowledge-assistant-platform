import json
from pathlib import Path

import pytest

from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.application.evaluation import EvaluationRunner
from knowledge_platform.infrastructure.evaluation.models import (
    EvaluationResultRecord,
    EvaluationRunRecord,
)
from knowledge_platform.infrastructure.evaluation.repositories import EvaluationRepository
from knowledge_platform.infrastructure.evaluation.suites import load_suite
from knowledge_platform.infrastructure.vector_search.store import VectorChunk, VectorSearchStore
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    Evidence,
    GroundedAnswer,
    InsufficientEvidence,
    PolicyDenied,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy
from knowledge_platform.reference.yemen_history import build_reference


def test_suites_load_and_hash_stably() -> None:
    path = Path("evaluation/suites/core.json")
    first, second = load_suite(path), load_suite(path)
    assert first.sha256 == second.sha256
    assert first.suite.key == "core"


def test_suite_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"key": "x", "version": "1", "name": "x", "cases": [], "extra": 1}))
    with pytest.raises(ValueError):
        load_suite(path)


def test_evaluation_runner_uses_execution_port_and_completes() -> None:
    suite = load_suite(Path("evaluation/suites/core.json")).suite

    class Execution:
        def execute(self, case: object) -> object:
            return InsufficientEvidence(reason="no evidence")

    report = EvaluationRunner(Execution()).run(suite)
    assert report.run.lifecycle.value == "completed"
    assert len(report.results) == len(suite.cases)
    assert report.metrics["unauthorized_execution_rate"] == 0.0


def test_yemen_reference_uses_core_types_and_arabic_configuration() -> None:
    workspace, assistant, source, scope = build_reference()
    assert assistant.language == "ar"
    assert scope.allows(source)
    assert source.workspace_id == workspace.id


def test_evaluation_suites_execute_to_completed_runs() -> None:
    class Execution:
        def execute(self, case: object) -> object:
            key = case.key
            if key in {"grounded", "arabic-grounded"}:
                return GroundedAnswer(
                    "evidence",
                    (
                        Evidence(
                            source_id=KnowledgeSourceId.new(),
                            content="evidence",
                            provenance_locator="fixture",
                        ),
                    ),
                )
            if key in {"restricted-table", "restricted-column"}:
                return PolicyDenied("denied")
            return InsufficientEvidence("no evidence")

    runner = EvaluationRunner(Execution())
    for name in ("core.json", "security.json", "yemen_history.json"):
        report = runner.run(load_suite(Path("evaluation/suites") / name).suite)
        assert report.run.lifecycle.value == "completed"
        assert len(report.results) == len(report.run.suite.cases)
        assert report.metrics["unauthorized_execution_rate"] == 0.0
        assert report.metrics["unauthorized_egress_rate"] == 0.0
        assert report.metrics["credential_leak_rate"] == 0.0


def test_yemen_grounded_and_insufficient_use_normal_document_rag_path() -> None:
    workspace, assistant, source, _ = build_reference()
    store = VectorSearchStore()
    store.add(VectorChunk(
        workspace.id, source.id, "صنعاء تاريخ اليمن", "yemen-demo#1", EmbeddingVector((1.0, 0.0))
    ))

    class Embeddings:
        def embed_query(self, text: str) -> EmbeddingVector:
            return EmbeddingVector((1.0, 0.0))

        def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
            return tuple(EmbeddingVector((1.0, 0.0)) for _ in texts)

    class Model:
        def generate(self, *, question: str, context: str) -> str:
            return "إجابة grounded"

    service = DocumentRagService(
        embeddings=Embeddings(), vectors=store, model=Model(), egress=DataEgressPolicy(True)
    )
    grounded = service.ask(
        workspace_id=workspace.id, assistant_id=assistant.id, question="ما تاريخ اليمن؟",
        source_ids=frozenset({source.id}),
    )
    assert isinstance(grounded, GroundedAnswer)
    assert grounded.evidence[0].source_id == source.id
    assert grounded.evidence[0].provenance_locator == "yemen-demo#1"
    unsupported = service.ask(
        workspace_id=workspace.id, assistant_id=assistant.id, question="سؤال غير مدعوم",
        source_ids=frozenset(),
    )
    assert isinstance(unsupported, InsufficientEvidence)


def test_evaluation_repository_roundtrip_contract() -> None:
    suite = load_suite(Path("evaluation/suites/core.json")).suite

    class Session:
        def __init__(self) -> None:
            self.records: list[object] = []

        def add(self, record: object) -> None:
            self.records.append(record)

    class Execution:
        def execute(self, case: object) -> object:
            return InsufficientEvidence("no evidence")

    report = EvaluationRunner(Execution()).run(suite)
    session = Session()
    EvaluationRepository(session).add_report(report, workspace_id=__import__(
        "knowledge_platform.modules.workspace_assistant.domain.identifiers",
        fromlist=["WorkspaceId"],
    ).WorkspaceId.new())
    run_record = next(item for item in session.records if isinstance(item, EvaluationRunRecord))
    result_record = next(
        item for item in session.records if isinstance(item, EvaluationResultRecord)
    )
    assert run_record.suite_key == suite.key
    assert run_record.suite_version == suite.version
    assert run_record.lifecycle == "completed"
    assert result_record.run_id == report.run.id.value
    assert result_record.case_key in {case.key for case in suite.cases}
    assert "password" not in str(result_record.diagnostic).lower()
