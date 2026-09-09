"""Contract checks for explicit pgvector query parameter typing."""

from unittest.mock import Mock

from sqlalchemy import Float

from knowledge_platform.infrastructure.vector_search.postgres import (
    PgvectorDocumentSearchAdapter,
)
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.retrieval_orchestration.domain.contracts import RetrievedContent
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


def test_retrieval_binds_query_operand_as_pgvector_without_changing_filters() -> None:
    session = Mock()
    session.execute.return_value.all.return_value = []
    workspace_id = WorkspaceId.new()
    source_id = KnowledgeSourceId.new()

    PgvectorDocumentSearchAdapter(session).search(
        workspace_id=workspace_id,
        source_ids=frozenset({source_id}),
        query=EmbeddingVector((0.0,) * 1024),
        limit=5,
    )

    statement, parameters = session.execute.call_args.args
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "document_chunks.embedding <=> :query_embedding" in compiled
    assert "AS distance" in compiled
    assert "distance" in statement.selected_columns.keys()
    assert isinstance(statement.selected_columns.distance.type, Float)
    assert statement._order_by_clauses
    assert "document_representations.workspace_id" in compiled
    assert "document_representations.source_id" in compiled
    assert "document_representations.state" in compiled
    assert "LIMIT" in compiled.upper()
    assert parameters["query_embedding"] == [0.0] * 1024
    query_bind = statement.compile().binds["query_embedding"]
    assert query_bind.type.__class__.__name__ == "VECTOR"
    assert query_bind.type.dim == 1024


def test_search_normalizes_rows_to_retrieved_content_contract() -> None:
    session = Mock()
    source_id = KnowledgeSourceId.new()
    chunk = Mock(content="safe evidence", provenance_locator="fixture#1")
    session.execute.return_value.all.return_value = [(chunk, source_id.value, 0.12)]

    result = PgvectorDocumentSearchAdapter(session).search(
        workspace_id=WorkspaceId.new(),
        source_ids=frozenset({source_id}),
        query=EmbeddingVector((0.0,) * 1024),
    )

    assert len(result) == 1
    item = result[0]
    assert isinstance(item, RetrievedContent)
    assert item.source_id == source_id
    assert item.content == "safe evidence"
    assert item.provenance_locator == "fixture#1"
    assert isinstance(item.distance, float)
    assert item.distance == 0.12
