"""Deterministic Stage 3 parser, retrieval, grounding, and egress contracts."""

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.infrastructure.documents.parsers import (
    DocxDocumentParser,
    JsonDocumentParser,
    PlainTextDocumentParser,
    PyPdfDocumentParser,
)
from knowledge_platform.infrastructure.documents.pipeline import chunk, normalize
from knowledge_platform.infrastructure.vector_search.postgres import PgvectorDocumentSearchAdapter
from knowledge_platform.infrastructure.vector_search.store import VectorChunk, VectorSearchStore
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    InsufficientEvidence,
    PolicyDenied,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy


class FakeEmbeddings:
    def embed_query(self, text: str) -> EmbeddingVector:
        return EmbeddingVector((1.0, 0.0))

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return tuple(EmbeddingVector((1.0, 0.0)) for _ in texts)


class FakeModel:
    calls = 0

    def generate(self, *, question: str, context: str) -> str:
        self.calls += 1
        return "Grounded response"


def test_txt_json_normalization_chunking_and_provenance() -> None:
    parsed = PlainTextDocumentParser().parse(b" A\r\n B ", reference="txt")
    normalized = normalize(parsed)
    chunks = chunk(normalized, size=3, overlap=1)
    assert chunks and all(item.provenance_locator == "txt" for item in chunks)
    json_doc = JsonDocumentParser().parse(json.dumps({"title": "Yemen"}).encode(), reference="json")
    assert json_doc.sections[0].provenance_locator == "json/title"


def test_empty_source_scope_is_empty_and_never_search_all() -> None:
    store = VectorSearchStore()
    store.add(
        VectorChunk(
            WorkspaceId.new(), KnowledgeSourceId.new(), "data", "loc", EmbeddingVector((1.0, 0.0))
        )
    )
    assert (
        store.search(
            workspace_id=WorkspaceId.new(),
            source_ids=frozenset(),
            query=EmbeddingVector((1.0, 0.0)),
        )
        == ()
    )


def test_document_rag_grounded_answer_preserves_evidence() -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    store = VectorSearchStore()
    store.add(
        VectorChunk(workspace_id, source_id, "Known fact", "json/a", EmbeddingVector((1.0, 0.0)))
    )
    model = FakeModel()
    outcome = DocumentRagService(
        embeddings=FakeEmbeddings(), vectors=store, model=model, egress=DataEgressPolicy(True)
    ).ask(
        workspace_id=workspace_id,
        assistant_id=AssistantId.new(),
        question="What?",
        source_ids=frozenset({source_id}),
    )
    assert isinstance(outcome, GroundedAnswer)
    assert outcome.evidence[0].provenance_locator == "json/a"
    assert model.calls == 1


def test_document_rag_insufficient_evidence_and_egress_denial() -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    model = FakeModel()
    service = DocumentRagService(
        embeddings=FakeEmbeddings(),
        vectors=VectorSearchStore(),
        model=model,
        egress=DataEgressPolicy(),
    )
    empty = service.ask(
        workspace_id=workspace_id,
        assistant_id=AssistantId.new(),
        question="What?",
        source_ids=frozenset({source_id}),
    )
    assert isinstance(empty, InsufficientEvidence)
    store = VectorSearchStore()
    store.add(
        VectorChunk(workspace_id, source_id, "Private fact", "loc", EmbeddingVector((1.0, 0.0)))
    )
    denied = DocumentRagService(
        embeddings=FakeEmbeddings(), vectors=store, model=model, egress=DataEgressPolicy()
    ).ask(
        workspace_id=workspace_id,
        assistant_id=AssistantId.new(),
        question="What?",
        source_ids=frozenset({source_id}),
    )
    assert isinstance(denied, PolicyDenied)
    assert model.calls == 0


def test_pgvector_search_short_circuits_empty_sources() -> None:
    class Session:
        def execute(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("empty source scope must not query the database")

    assert PgvectorDocumentSearchAdapter(Session()).search(
        workspace_id=WorkspaceId.new(), source_ids=frozenset(),
        query=EmbeddingVector((1.0, 0.0)),
    ) == ()


def test_docx_adapter_real_fixture() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            "<document xmlns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            "<body><p><r><t>Direct DOCX fixture</t></r></p></body></document>",
        )
    parsed = DocxDocumentParser().parse(buffer.getvalue(), reference="fixture.docx")
    assert "Direct DOCX fixture" in parsed.sections[0].content


def test_pdf_adapter_real_fixture() -> None:
    content = b"%PDF-1.4\nBT (Direct PDF fixture) Tj ET\n%%EOF"
    parsed = PyPdfDocumentParser().parse(content, reference="fixture.pdf")
    assert "Direct PDF fixture" in parsed.sections[0].content
