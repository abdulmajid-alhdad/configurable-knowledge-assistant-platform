"""PostgreSQL/pgvector retrieval adapters (transaction-owned by callers)."""

from collections.abc import Sequence

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from knowledge_platform.infrastructure.documents.representations import (
    DocumentRepresentation,
    RepresentationState,
)
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

from ..persistence.models import DocumentChunkRecord, DocumentRepresentationRecord


class DocumentRepresentationRepository:
    """Persists complete representations without owning transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, representation: DocumentRepresentation) -> None:
        self._session.add(
            DocumentRepresentationRecord(
                id=representation.id,
                workspace_id=representation.workspace_id.value,
                source_id=representation.source_id.value,
                version=representation.version,
                embedding_profile=representation.embedding_profile,
                dimensions=representation.dimensions,
                state=representation.state.value,
            )
        )
        for chunk in representation.chunks:
            self._session.add(
                DocumentChunkRecord(
                    representation_id=representation.id,
                    sequence=chunk.sequence,
                    content=chunk.content,
                    provenance_locator=chunk.provenance_locator,
                    embedding=list(getattr(chunk, "embedding", ())),
                )
            )

    def activate(
        self, *, representation: DocumentRepresentation, workspace_id: WorkspaceId
    ) -> None:
        if representation.state is not RepresentationState.ACTIVE:
            raise ValueError("only an ACTIVE representation can be activated")
        self._session.execute(
            update(DocumentRepresentationRecord)
            .where(
                DocumentRepresentationRecord.id == representation.id,
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
            )
            .values(state=RepresentationState.ACTIVE.value)
        )
        self._session.execute(
            update(DocumentRepresentationRecord)
            .where(
                DocumentRepresentationRecord.source_id == representation.source_id.value,
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
                DocumentRepresentationRecord.id != representation.id,
                DocumentRepresentationRecord.state == RepresentationState.ACTIVE.value,
            )
            .values(state=RepresentationState.RETIRED.value)
        )


class PgvectorDocumentSearchAdapter:
    """Parameterized ACTIVE-only vector search boundary."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        *,
        workspace_id: WorkspaceId,
        source_ids: frozenset[KnowledgeSourceId],
        query: EmbeddingVector,
        limit: int = 5,
    ) -> Sequence[object]:
        if not source_ids or limit <= 0:
            return ()
        statement = (
            select(DocumentChunkRecord)
            .join(
                DocumentRepresentationRecord,
                DocumentChunkRecord.representation_id == DocumentRepresentationRecord.id,
            )
            .where(
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
                DocumentRepresentationRecord.source_id.in_([item.value for item in source_ids]),
                DocumentRepresentationRecord.state == RepresentationState.ACTIVE.value,
            )
            .order_by(text("document_chunks.embedding <=> :query_embedding"))
            .limit(limit)
        )
        return self._session.execute(
            statement, {"query_embedding": list(query.values)}
        ).scalars().all()
