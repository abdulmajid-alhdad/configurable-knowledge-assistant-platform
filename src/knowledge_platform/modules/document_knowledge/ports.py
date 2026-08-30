"""Provider-neutral Stage 3 ports."""

from dataclasses import dataclass
from typing import Protocol

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ParsedDocumentSection:
    content: str
    provenance_locator: str


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    sections: tuple[ParsedDocumentSection, ...]


class DocumentParserPort(Protocol):
    def parse(self, content: bytes, *, reference: str = "document") -> ParsedDocument: ...


class EmbeddingGatewayPort(Protocol):
    def embed_query(self, text: str) -> EmbeddingVector: ...
    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]: ...


class ModelPort(Protocol):
    def generate(self, *, question: str, context: str) -> str: ...


class VectorSearchPort(Protocol):
    def search(
        self,
        *,
        workspace_id: WorkspaceId,
        source_ids: frozenset[KnowledgeSourceId],
        query: EmbeddingVector,
        limit: int = 5,
    ) -> tuple[object, ...]: ...
