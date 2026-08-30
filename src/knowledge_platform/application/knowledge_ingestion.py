"""Product-level upload and reprocessing orchestration."""

from collections.abc import Callable, Iterable
from typing import Any, Protocol

from knowledge_platform.application.document_ingestion import DocumentIngestionService
from knowledge_platform.modules.document_knowledge.artifacts import (
    OriginalArtifact,
    OriginalArtifactStorePort,
)
from knowledge_platform.modules.document_knowledge.ports import DocumentParserPort
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class SourceRepositoryPort(Protocol):
    def save_transition(self, *, previous: KnowledgeSource, transitioned: KnowledgeSource,
                        workspace_id: WorkspaceId) -> None: ...


class RepresentationRepositoryPort(Protocol):
    def add(self, representation: Any) -> None: ...
    def activate(self, *, representation: Any, workspace_id: WorkspaceId) -> None: ...


class KnowledgeIngestionService:
    def __init__(self, *, artifacts: OriginalArtifactStorePort,
                 ingestion: DocumentIngestionService, max_artifact_bytes: int,
                 parser_factory: Callable[[str], DocumentParserPort]) -> None:
        self._artifacts = artifacts
        self._ingestion = ingestion
        self._max_bytes = max_artifact_bytes
        self._parser_factory = parser_factory

    def upload(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId,
               chunks: Iterable[bytes], filename: str,
               media_type: str | None) -> OriginalArtifact:
        return self._artifacts.store(
            workspace_id=workspace_id, source_id=source_id, chunks=chunks,
            filename=filename, media_type=media_type, max_bytes=self._max_bytes,
        )

    def process(self, *, workspace_id: WorkspaceId, source: KnowledgeSource,
                representation_repository: RepresentationRepositoryPort,
                embedding_profile: str, source_repository: SourceRepositoryPort) -> KnowledgeSource:
        artifact = self._artifacts.get(workspace_id=workspace_id, source_id=source.id)
        if artifact is None:
            raise FileNotFoundError("original artifact is not stored")
        parser = self._parser_factory(artifact.suffix)
        return self._ingestion.ingest(
            source=source, raw=self._artifacts.retrieve(artifact),
            reference=f"{artifact.original_filename}", parser=parser,
            source_repository=source_repository,
            representation_repository=representation_repository,
            workspace_id=workspace_id, embedding_profile=embedding_profile,
        )
