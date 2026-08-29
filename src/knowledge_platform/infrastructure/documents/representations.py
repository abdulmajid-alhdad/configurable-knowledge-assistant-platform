"""Versioned derived document representations."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

from .pipeline import DocumentChunk


class RepresentationState(StrEnum):
    BUILDING = "BUILDING"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class DocumentRepresentation:
    id: UUID
    workspace_id: WorkspaceId
    source_id: KnowledgeSourceId
    version: int
    embedding_profile: str
    dimensions: int
    state: RepresentationState
    chunks: tuple[DocumentChunk, ...]

    @classmethod
    def building(
        cls,
        *,
        workspace_id: WorkspaceId,
        source_id: KnowledgeSourceId,
        version: int,
        embedding_profile: str,
        dimensions: int,
        chunks: tuple[DocumentChunk, ...],
    ) -> "DocumentRepresentation":
        if version <= 0 or dimensions <= 0 or not chunks:
            raise ValueError("invalid document representation")
        return cls(
            uuid4(),
            workspace_id,
            source_id,
            version,
            embedding_profile,
            dimensions,
            RepresentationState.BUILDING,
            chunks,
        )

    def activate(self) -> "DocumentRepresentation":
        if self.state is not RepresentationState.BUILDING:
            raise ValueError("only BUILDING representations can activate")
        return DocumentRepresentation(
            self.id,
            self.workspace_id,
            self.source_id,
            self.version,
            self.embedding_profile,
            self.dimensions,
            RepresentationState.ACTIVE,
            self.chunks,
        )
