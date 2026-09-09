"""Safe first-failure diagnostics for RAG database operations."""

import pytest

from knowledge_platform.application.document_rag import (
    DatabaseRetrievalFailure,
    DocumentRagService,
    _log_rag_failure,
)
from knowledge_platform.modules.document_knowledge.ports import (
    EmbeddingVector,
    GroundedModelAnswer,
)
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    InsufficientEvidence,
    TechnicalFailure,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.retrieval_orchestration.domain.contracts import RetrievedContent
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy


class _Embeddings:
    def embed_query(self, text: str) -> EmbeddingVector:
        return EmbeddingVector((1.0,))


class _DatabaseDiagnostics:
    sqlstate = "22P02"
    constraint_name = ""
    table_name = "document_chunks"
    schema_name = "retrieval"


class _Vectors:
    def search(self, **kwargs: object) -> tuple[object, ...]:
        raise DatabaseRetrievalFailure(
            sqlstate=_DatabaseDiagnostics.sqlstate,
            table_name=_DatabaseDiagnostics.table_name,
            schema_name=_DatabaseDiagnostics.schema_name,
        )


class _Model:
    def generate(self, *, question: str, context: str) -> GroundedModelAnswer:
        raise AssertionError("model must not run after retrieval failure")


class _Chunk:
    source_id = KnowledgeSourceId.new()
    content = "safe evidence"
    provenance_locator = "fixture#1"


class _FailingModel:
    def generate(self, *, question: str, context: str) -> GroundedModelAnswer:
        raise RuntimeError("SECRET_PROMPT SECRET_MODEL_RESPONSE SECRET_TOKEN")


def test_rag_failure_logger_handles_attribute_error_without_raw_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = AttributeError("SECRET_EVIDENCE SECRET_VECTOR SECRET_SQL")
    workspace_id = WorkspaceId.new()
    with caplog.at_level("ERROR", logger="knowledge_platform.application.document_rag"):
        _log_rag_failure(workspace_id=workspace_id, stage="evidence_mapping", error=error)

    assert "rag_operation_failed" in caplog.text
    assert "stage=evidence_mapping" in caplog.text
    assert "exception_type=AttributeError" in caplog.text
    assert "SECRET_" not in caplog.text


def test_evidence_mapping_preserves_source_and_provenance_and_reaches_model() -> None:
    source_id = KnowledgeSourceId.new()
    calls: list[str] = []

    class Vectors:
        def search(self, **kwargs: object) -> tuple[object, ...]:
            return (_ChunkWithSource(source_id),)

    class Model:
        def generate(self, *, question: str, context: str) -> GroundedModelAnswer:
            calls.append(context)
            return GroundedModelAnswer("safe answer", ("E1",))

    result = DocumentRagService(
        embeddings=_Embeddings(), vectors=Vectors(), model=Model(), egress=DataEgressPolicy(True)
    ).ask(
        workspace_id=WorkspaceId.new(),
        assistant_id=AssistantId.new(),
        question="supported question",
        source_ids=frozenset({source_id}),
    )

    assert isinstance(result, GroundedAnswer)
    assert result.evidence[0].source_id == source_id
    assert result.evidence[0].provenance_locator == "fixture#1"
    assert len(calls) == 1
    assert "Answer only from the supplied evidence" in calls[0]
    assert "safe evidence" in calls[0]


class _ChunkWithSource:
    content = "safe evidence"
    provenance_locator = "fixture#1"

    def __init__(self, source_id: KnowledgeSourceId) -> None:
        self.source_id = source_id


def test_retrieved_content_distance_filters_weak_evidence_without_model_call() -> None:
    source_id = KnowledgeSourceId.new()
    calls = 0

    class Vectors:
        def search(self, **kwargs: object) -> tuple[object, ...]:
            return (
                RetrievedContent(
                    source_id=source_id,
                    content="unrelated evidence",
                    provenance_locator="fixture#weak",
                    distance=0.9,
                ),
            )

    class Model:
        def generate(self, *, question: str, context: str) -> GroundedModelAnswer:
            nonlocal calls
            calls += 1
            return GroundedModelAnswer("must not run", ("E1",))

    result = DocumentRagService(
        embeddings=_Embeddings(),
        vectors=Vectors(),
        model=Model(),
        egress=DataEgressPolicy(True),
        max_retrieval_distance=0.4,
    ).ask(
        workspace_id=WorkspaceId.new(),
        assistant_id=AssistantId.new(),
        question="unsupported question",
        source_ids=frozenset({source_id}),
    )
    assert isinstance(result, InsufficientEvidence)
    assert calls == 0


def test_evidence_mapping_failure_is_safe_and_does_not_call_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenChunk:
        source_id = KnowledgeSourceId.new()

        @property
        def content(self) -> str:
            raise AttributeError("SECRET_CHUNK SECRET_EVIDENCE")

        provenance_locator = "fixture#broken"

    class Vectors:
        def search(self, **kwargs: object) -> tuple[object, ...]:
            return (BrokenChunk(),)

    class Model:
        def generate(self, *, question: str, context: str) -> GroundedModelAnswer:
            raise AssertionError("model must not run after evidence mapping failure")

    with caplog.at_level("ERROR", logger="knowledge_platform.application.document_rag"):
        result = DocumentRagService(
            embeddings=_Embeddings(),
            vectors=Vectors(),
            model=Model(),
            egress=DataEgressPolicy(True),
        ).ask(
            workspace_id=WorkspaceId.new(),
            assistant_id=AssistantId.new(),
            question="SECRET_QUESTION",
            source_ids=frozenset({BrokenChunk.source_id}),
        )

    assert isinstance(result, TechnicalFailure)
    assert result.reason == "document RAG failed"
    assert "stage=evidence_mapping" in caplog.text
    assert "exception_type=AttributeError" in caplog.text
    assert "SECRET_" not in caplog.text


def test_first_rag_database_failure_is_logged_without_raw_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    workspace_id = WorkspaceId.new()
    source_id = KnowledgeSourceId.new()
    with caplog.at_level("ERROR", logger="knowledge_platform.application.document_rag"):
        with pytest.raises(DatabaseRetrievalFailure):
            DocumentRagService(
                embeddings=_Embeddings(),
                vectors=_Vectors(),
                model=_Model(),
                egress=DataEgressPolicy(True),
            ).ask(
                workspace_id=workspace_id,
                assistant_id=AssistantId.new(),
                question="SECRET_QUESTION",
                source_ids=frozenset({source_id}),
            )

    assert "rag_database_operation_failed" in caplog.text
    assert "sqlstate=22P02" in caplog.text
    assert "table_name=document_chunks" in caplog.text
    assert "schema_name=retrieval" in caplog.text
    assert "exception_type=DatabaseRetrievalFailure" in caplog.text
    for secret in (
        "SECRET_QUESTION",
        "SECRET_SQL",
        "SECRET_PARAMETER",
        "SECRET_CHUNK",
        "SECRET_TOKEN",
        "SECRET_DSN",
    ):
        assert secret not in caplog.text


def test_non_database_rag_failure_uses_only_safe_reason() -> None:
    class Failure:
        def embed_query(self, text: str) -> EmbeddingVector:
            raise RuntimeError("SECRET_QUESTION SECRET_TOKEN SECRET_DSN")

    result = DocumentRagService(
        embeddings=Failure(),
        vectors=_Vectors(),
        model=_Model(),
        egress=DataEgressPolicy(True),
    ).ask(
        workspace_id=WorkspaceId.new(),
        assistant_id=AssistantId.new(),
        question="question",
        source_ids=frozenset({KnowledgeSourceId.new()}),
    )

    assert isinstance(result, TechnicalFailure)
    assert result.reason == "document RAG failed"
    for secret in ("SECRET_QUESTION", "SECRET_TOKEN", "SECRET_DSN"):
        assert secret not in result.reason


def test_query_embedding_failure_logs_stage_and_safe_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Embeddings:
        def embed_query(self, text: str) -> EmbeddingVector:
            raise RuntimeError("SECRET_EMBEDDING SECRET_TOKEN")

    with caplog.at_level("ERROR", logger="knowledge_platform.application.document_rag"):
        result = DocumentRagService(
            embeddings=Embeddings(), vectors=_Vectors(), model=_Model(),
            egress=DataEgressPolicy(True),
        ).ask(
            workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new(),
            question="SECRET_QUESTION", source_ids=frozenset({KnowledgeSourceId.new()}),
        )
    assert isinstance(result, TechnicalFailure)
    assert result.reason == "document RAG failed"
    assert "stage=query_embedding" in caplog.text
    assert "SECRET_" not in caplog.text


def test_model_failure_logs_model_stage_without_private_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Vectors:
        def search(self, **kwargs: object) -> tuple[object, ...]:
            return (_Chunk(),)

    with caplog.at_level("ERROR", logger="knowledge_platform.application.document_rag"):
        result = DocumentRagService(
            embeddings=_Embeddings(), vectors=Vectors(), model=_FailingModel(),
            egress=DataEgressPolicy(True),
        ).ask(
            workspace_id=WorkspaceId.new(), assistant_id=AssistantId.new(),
            question="question", source_ids=frozenset({_Chunk.source_id}),
        )
    assert isinstance(result, TechnicalFailure)
    assert result.reason == "document RAG failed"
    assert "stage=model_generation" in caplog.text
    assert "SECRET_" not in caplog.text
