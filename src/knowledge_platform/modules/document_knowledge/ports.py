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


@dataclass(frozen=True, slots=True)
class GroundedModelAnswer:
    """Provider-neutral grounded generation result."""

    answer: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str) or not self.answer.strip():
            raise ValueError("grounded model answer must not be blank")
        if not isinstance(self.evidence_ids, tuple) or not self.evidence_ids:
            raise ValueError("grounded model answer requires evidence ids")
        if not all(isinstance(item, str) and item.strip() for item in self.evidence_ids):
            raise ValueError("grounded model evidence ids must be nonblank strings")


@dataclass(frozen=True, slots=True)
class ModelInsufficientEvidence:
    """Model disposition indicating supplied evidence cannot answer the question."""


ModelGenerationResult = GroundedModelAnswer | ModelInsufficientEvidence


class ModelPort(Protocol):
    def generate(
        self, *, question: str, context: str, assistant_instructions: str | None = None
    ) -> ModelGenerationResult: ...


class VectorSearchPort(Protocol):
    def search(
        self,
        *,
        workspace_id: WorkspaceId,
        source_ids: frozenset[KnowledgeSourceId],
        query: EmbeddingVector,
        limit: int = 5,
    ) -> tuple[object, ...]: ...
