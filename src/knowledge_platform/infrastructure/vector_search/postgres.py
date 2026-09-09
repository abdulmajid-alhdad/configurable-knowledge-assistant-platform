"""PostgreSQL/pgvector retrieval adapters (transaction-owned by callers)."""

from collections.abc import Sequence

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import bindparam, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from knowledge_platform.application.document_rag import DatabaseRetrievalFailure
from knowledge_platform.infrastructure.documents.representations import (
    DocumentRepresentation,
    RepresentationState,
)
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.retrieval_orchestration.domain.contracts import RetrievedContent
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
        # Make the parent row visible to the chunk RLS subquery before the
        # child rows are flushed under the same workspace transaction.
        self._session.flush()
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

    def next_version(self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId) -> int:
        current = self._session.scalar(
            select(func.max(DocumentRepresentationRecord.version)).where(
                DocumentRepresentationRecord.source_id == source_id.value,
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
            )
        )
        return int(current or 0) + 1

    def activate(
        self, *, representation: DocumentRepresentation, workspace_id: WorkspaceId
    ) -> None:
        if representation.state is not RepresentationState.ACTIVE:
            raise ValueError("only an ACTIVE representation can be activated")
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
        self._session.flush()
        self._session.execute(
            update(DocumentRepresentationRecord)
            .where(
                DocumentRepresentationRecord.id == representation.id,
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
            )
            .values(state=RepresentationState.ACTIVE.value)
        )

    def retire_active_for_source(
        self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId
    ) -> None:
        """Remove a source's representations from the searchable ACTIVE set."""
        self._session.execute(
            update(DocumentRepresentationRecord)
            .where(
                DocumentRepresentationRecord.source_id == source_id.value,
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
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
        query_parameter = bindparam(
            "query_embedding", type_=VECTOR(len(query.values))
        )
        # Use pgvector's comparator so the operator remains ``<=>`` while its
        # scalar result is typed as Float (rather than inheriting VECTOR from
        # the embedding column).  The explicitly typed bind keeps the right
        # operand a VECTOR, not an array.
        distance = DocumentChunkRecord.embedding.cosine_distance(query_parameter)
        statement = (
            select(
                DocumentChunkRecord,
                DocumentRepresentationRecord.source_id,
                distance.label("distance"),
            )
            .join(
                DocumentRepresentationRecord,
                DocumentChunkRecord.representation_id == DocumentRepresentationRecord.id,
            )
            .where(
                DocumentRepresentationRecord.workspace_id == workspace_id.value,
                DocumentRepresentationRecord.source_id.in_([item.value for item in source_ids]),
                DocumentRepresentationRecord.state == RepresentationState.ACTIVE.value,
            )
            .order_by(distance)
            .limit(limit)
        )
        try:
            rows = self._session.execute(
                statement, {"query_embedding": list(query.values)}
            ).all()
            return tuple(
                RetrievedContent(
                    source_id=KnowledgeSourceId(source_id),
                    content=chunk.content,
                    provenance_locator=chunk.provenance_locator,
                    distance=float(chunk_distance),
                )
                for chunk, source_id, chunk_distance in rows
            )
        except SQLAlchemyError as exc:
            original = getattr(exc, "orig", None)
            diag = getattr(exc, "diag", None) or getattr(original, "diag", None)
            raise DatabaseRetrievalFailure(
                sqlstate=getattr(diag, "sqlstate", None),
                constraint_name=getattr(diag, "constraint_name", None),
                table_name=getattr(diag, "table_name", None),
                schema_name=getattr(diag, "schema_name", None),
            ) from None
