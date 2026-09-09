"""Deterministic Stage 3 parser, retrieval, grounding, and egress contracts."""

import json
from io import BytesIO

import pytest

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
from knowledge_platform.modules.document_knowledge.ports import (
    EmbeddingVector,
    GroundedModelAnswer,
)
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

    def generate(self, *, question: str, context: str) -> GroundedModelAnswer:
        self.calls += 1
        return GroundedModelAnswer("Grounded response", ("E1",))


def test_txt_json_normalization_chunking_and_provenance() -> None:
    parsed = PlainTextDocumentParser().parse(b" A\r\n B ", reference="txt")
    normalized = normalize(parsed)
    chunks = chunk(normalized, size=3, overlap=1)
    assert chunks and all(item.provenance_locator == "txt" for item in chunks)
    json_doc = JsonDocumentParser().parse(json.dumps({"title": "Yemen"}).encode(), reference="json")
    assert json_doc.sections[0].provenance_locator == "json"
    assert "title: Yemen" in json_doc.sections[0].content


def test_json_root_array_preserves_record_boundaries() -> None:
    parsed = JsonDocumentParser().parse(
        json.dumps([{"name": "first"}, {"name": "second"}]).encode(),
        reference="dataset.json",
    )
    assert [section.provenance_locator for section in parsed.sections] == [
        "dataset.json/0", "dataset.json/1"
    ]
    assert "first" in parsed.sections[0].content
    assert "second" in parsed.sections[1].content
    assert "second" not in parsed.sections[0].content


def test_json_nested_record_textualizes_paths_and_omits_nulls() -> None:
    parsed = JsonDocumentParser().parse(
        b'{"meta":{"count":2,"enabled":true,"missing":null}}',
        reference="record.json",
    )
    assert len(parsed.sections) == 1
    text = parsed.sections[0].content
    assert "meta.count: 2" in text
    assert "meta.enabled: True" in text
    assert "None" not in text


def test_json_messages_are_one_semantic_record() -> None:
    parsed = JsonDocumentParser().parse(
        json.dumps(
            [{"messages": [{"role": "user", "content": "question"},
                            {"role": "assistant", "content": "answer"}]}]
        ).encode(),
        reference="dataset.json",
    )
    assert len(parsed.sections) == 1
    assert "messages.0.role: user" in parsed.sections[0].content
    assert "messages.0.content: question" in parsed.sections[0].content
    assert "messages.1.role: assistant" in parsed.sections[0].content
    assert "messages.1.content: answer" in parsed.sections[0].content


def test_json_record_provenance_survives_normalize_and_chunk() -> None:
    parsed = JsonDocumentParser().parse(b'[{"value":"kept"}]', reference="dataset.json")
    normalized = normalize(parsed)
    chunks = chunk(normalized)
    assert len(chunks) == 1
    assert chunks[0].provenance_locator == "dataset.json/0"
    assert "value: kept" in chunks[0].content


def test_json_large_record_can_split_while_retaining_record_provenance() -> None:
    parsed = JsonDocumentParser().parse(
        json.dumps({"text": "x" * 1700}).encode(), reference="large.json"
    )
    chunks = chunk(normalize(parsed), size=800, overlap=80)
    assert len(chunks) > 1
    assert all(item.provenance_locator == "large.json" for item in chunks)


def test_json_parser_accepts_utf8_bom_without_changing_sections() -> None:
    payload = json.dumps(
        {"title": "Yemen", "items": [{"name": "Sanaa"}, "historical"]}
    ).encode("utf-8")
    parser = JsonDocumentParser()

    ordinary = parser.parse(payload, reference="dataset.json")
    with_bom = parser.parse(b"\xef\xbb\xbf" + payload, reference="dataset.json")

    assert with_bom == ordinary


def test_json_parser_rejects_malformed_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        JsonDocumentParser().parse(b'{"title":', reference="dataset.json")


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
    from docx import Document as DocxDocument

    buffer = BytesIO()
    document = DocxDocument()
    document.add_paragraph("Direct DOCX fixture")
    document.save(buffer)
    parsed = DocxDocumentParser().parse(buffer.getvalue(), reference="fixture.docx")
    assert "Direct DOCX fixture" in parsed.sections[0].content
    assert parsed.sections[0].provenance_locator.startswith("fixture.docx#paragraph-")


def test_pdf_adapter_real_fixture() -> None:
    content = b"%PDF-1.4\nBT (Direct PDF fixture) Tj ET\n%%EOF"
    parsed = PyPdfDocumentParser().parse(content, reference="fixture.pdf")
    assert "Direct PDF fixture" in parsed.sections[0].content
