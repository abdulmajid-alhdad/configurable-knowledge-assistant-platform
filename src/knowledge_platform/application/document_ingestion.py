"""Application-owned document preparation and KnowledgeSource lifecycle flow."""

from dataclasses import replace
from typing import Any

from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceLifecycle
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId
from knowledge_platform.modules.workspace_assistant.domain.security import (
    DataEgressPolicy,
    PolicyDecision,
    ProcessingLocation,
)


class DocumentIngestionService:
    """Coordinates preparation, representation activation, and source readiness."""

    def __init__(self, *, embeddings: Any, egress: DataEgressPolicy) -> None:
        self._embeddings = embeddings
        self._egress = egress

    def ingest(
        self,
        *,
        source: KnowledgeSource,
        raw: bytes,
        reference: str,
        parser: Any,
        source_repository: Any,
        representation_repository: Any,
        workspace_id: WorkspaceId,
        embedding_profile: str,
        reindex: bool = False,
    ) -> KnowledgeSource:
        if source.workspace_id != workspace_id:
            raise ValueError("knowledge source workspace does not match persistence workspace")
        if reindex:
            if source.lifecycle is not KnowledgeSourceLifecycle.READY:
                raise ValueError("reindex requires a READY knowledge source")
            preparing = source
        elif source.lifecycle is KnowledgeSourceLifecycle.PREPARING:
            preparing = source
        else:
            preparing = source.begin_preparation()
            source_repository.save_transition(
                previous=source, transitioned=preparing, workspace_id=workspace_id
            )
        try:
            pipeline = __import__(
                "knowledge_platform.infrastructure.documents.pipeline",
                fromlist=["chunk", "normalize"],
            )
            representation_module = __import__(
                "knowledge_platform.infrastructure.documents.representations",
                fromlist=["DocumentRepresentation"],
            )
            chunk, normalize = pipeline.chunk, pipeline.normalize
            DocumentRepresentation = representation_module.DocumentRepresentation

            prepared = normalize(parser.parse(raw, reference=reference))
            chunks = chunk(prepared)
            if self._egress.decide(
                processing_location=ProcessingLocation.EXTERNAL,
                contains_private_data=True,
            ) is PolicyDecision.DENY:
                raise PermissionError("external private-data egress denied")
            vectors = self._embeddings.embed_documents(tuple(item.content for item in chunks))
            if len(vectors) != len(chunks):
                raise ValueError("embedding count does not match chunk count")
            embedded = tuple(
                replace(item, embedding=vector.values)
                for item, vector in zip(chunks, vectors, strict=True)
            )
            representation = DocumentRepresentation.building(
                workspace_id=workspace_id,
                source_id=source.id,
                version=representation_repository.next_version(
                    source_id=source.id, workspace_id=workspace_id
                ),
                embedding_profile=embedding_profile,
                dimensions=len(vectors[0].values),
                chunks=embedded,
            )
            representation_repository.add(representation)
            active = representation.activate()
            representation_repository.activate(representation=active, workspace_id=workspace_id)
            ready = preparing if reindex else preparing.mark_ready()
            if not reindex:
                source_repository.save_transition(
                    previous=preparing, transitioned=ready, workspace_id=workspace_id
                )
            return ready
        except Exception:
            raise
