"""Workspace/source-scoped vector retrieval contract and deterministic fake store."""

from dataclasses import dataclass

from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


@dataclass(frozen=True, slots=True)
class VectorChunk:
    workspace_id: WorkspaceId
    source_id: KnowledgeSourceId
    content: str
    provenance_locator: str
    vector: EmbeddingVector
    active: bool = True


class VectorSearchStore:
    def __init__(self) -> None:
        self._chunks: list[VectorChunk] = []

    def add(self, chunk: VectorChunk) -> None:
        self._chunks.append(chunk)

    def search(
        self,
        *,
        workspace_id: WorkspaceId,
        source_ids: frozenset[KnowledgeSourceId],
        query: EmbeddingVector,
        limit: int = 5,
    ) -> tuple[VectorChunk, ...]:
        if not source_ids or limit <= 0:
            return ()
        candidates = [
            c
            for c in self._chunks
            if c.active and c.workspace_id == workspace_id and c.source_id in source_ids
        ]

        def score(c: VectorChunk) -> float:
            return sum(a * b for a, b in zip(c.vector.values, query.values, strict=False))

        return tuple(sorted(candidates, key=score, reverse=True)[:limit])
