"""Contract checks for parent-first retrieval persistence ordering."""

from unittest.mock import Mock

from knowledge_platform.infrastructure.documents.pipeline import DocumentChunk
from knowledge_platform.infrastructure.documents.representations import (
    DocumentRepresentation,
)
from knowledge_platform.infrastructure.vector_search.postgres import (
    DocumentRepresentationRepository,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


def test_representation_repository_flushes_parent_before_chunks() -> None:
    session = Mock()
    workspace_id = WorkspaceId.new()
    source_id = KnowledgeSourceId.new()
    representation = DocumentRepresentation.building(
        workspace_id=workspace_id,
        source_id=source_id,
        version=1,
        embedding_profile="test",
        dimensions=2,
        chunks=(
            DocumentChunk(
                "content", "dataset.json/title", 0, (0.1, 0.2)
            ),
        ),
    )

    DocumentRepresentationRepository(session).add(representation)

    assert session.flush.call_count == 1
    assert session.add.call_count == 2
    assert session.add.call_args_list[0].args[0].__tablename__ == "document_representations"
    assert session.add.call_args_list[1].args[0].__tablename__ == "document_chunks"
