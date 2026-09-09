"""Remote embedding egress must be decided before provider invocation."""
from unittest.mock import Mock

import pytest

from knowledge_platform.application.document_ingestion import DocumentIngestionService
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.infrastructure.documents.parsers import MarkdownDocumentParser
from knowledge_platform.infrastructure.vector_search.store import VectorSearchStore
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.evidence_grounding.domain.contracts import PolicyDenied
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy
from knowledge_platform.reference.yemen_history import build_reference


def test_query_embedding_is_not_called_when_private_egress_is_denied() -> None:
    workspace, assistant, source, _ = build_reference()
    calls = 0

    class Embeddings:
        def embed_query(self, text: str) -> EmbeddingVector:
            nonlocal calls
            calls += 1
            return EmbeddingVector((1.0,))

    class Model:
        def generate(self, *, question: str, context: str) -> str:
            raise AssertionError("model must not run after egress denial")

    result = DocumentRagService(
        embeddings=Embeddings(), vectors=VectorSearchStore(), model=Model(),
        egress=DataEgressPolicy(False),
    ).ask(
        workspace_id=workspace.id, assistant_id=assistant.id,
        question="private question", source_ids=frozenset({source.id}), private_data=True,
    )
    assert isinstance(result, PolicyDenied)
    assert calls == 0


def test_ingestion_denial_prevents_embedding_and_ready_transition() -> None:
    workspace_id = WorkspaceId.new()
    source = KnowledgeSource.create(
        workspace_id=workspace_id, name="private", kind=KnowledgeSourceKind.DOCUMENT
    )
    source_repository = Mock()
    representation_repository = Mock()
    embeddings = Mock()
    service = DocumentIngestionService(
        embeddings=embeddings, egress=DataEgressPolicy()
    )

    with pytest.raises(PermissionError, match="egress denied"):
        service.ingest(
            source=source,
            raw=b"private content",
            reference="private.md",
            parser=MarkdownDocumentParser(),
            source_repository=source_repository,
            representation_repository=representation_repository,
            workspace_id=workspace_id,
            embedding_profile="test",
        )

    embeddings.embed_documents.assert_not_called()
    assert source_repository.save_transition.call_count == 1
    representation_repository.add.assert_not_called()


def test_ingestion_embedding_is_allowed_by_explicit_external_policy() -> None:
    workspace_id = WorkspaceId.new()
    source = KnowledgeSource.create(
        workspace_id=workspace_id, name="private", kind=KnowledgeSourceKind.DOCUMENT
    )
    source_repository = Mock()
    representation_repository = Mock()
    embeddings = Mock()
    embeddings.embed_documents.return_value = (EmbeddingVector((1.0,)),)
    ready = DocumentIngestionService(
        embeddings=embeddings,
        egress=DataEgressPolicy(external_private_data_allowed=True),
    ).ingest(
        source=source,
        raw=b"private content",
        reference="private.md",
        parser=MarkdownDocumentParser(),
        source_repository=source_repository,
        representation_repository=representation_repository,
        workspace_id=workspace_id,
        embedding_profile="test",
    )

    embeddings.embed_documents.assert_called_once()
    assert ready.lifecycle.value == "ready"


def test_ingestion_uses_durable_preparing_state_for_failure_transition() -> None:
    workspace_id = WorkspaceId.new()
    source = KnowledgeSource.create(
        workspace_id=workspace_id, name="private", kind=KnowledgeSourceKind.DOCUMENT
    ).begin_preparation()
    source_repository = Mock()
    representation_repository = Mock()
    embeddings = Mock()

    with pytest.raises(PermissionError, match="egress denied"):
        DocumentIngestionService(
            embeddings=embeddings, egress=DataEgressPolicy()
        ).ingest(
            source=source,
            raw=b"private content",
            reference="private.md",
            parser=MarkdownDocumentParser(),
            source_repository=source_repository,
            representation_repository=representation_repository,
            workspace_id=workspace_id,
            embedding_profile="test",
        )

    source_repository.save_transition.assert_not_called()
