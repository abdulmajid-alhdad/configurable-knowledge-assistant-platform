"""Product-level upload and reprocessing orchestration."""

from knowledge_platform.application.document_ingestion import DocumentIngestionService
from knowledge_platform.modules.document_knowledge.artifacts import OriginalArtifactStorePort
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class KnowledgeIngestionService:
    def __init__(self, *, artifacts: OriginalArtifactStorePort,
                 ingestion: DocumentIngestionService, max_artifact_bytes: int,
                 parser_factory) -> None:
        self._artifacts = artifacts
        self._ingestion = ingestion
        self._max_bytes = max_artifact_bytes
        self._parser_factory = parser_factory

    def upload(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId,
               chunks, filename: str, media_type: str | None):
        return self._artifacts.store(
            workspace_id=workspace_id, source_id=source_id, chunks=chunks,
            filename=filename, media_type=media_type, max_bytes=self._max_bytes,
        )

    def process(self, *, workspace_id: WorkspaceId, source, source_repository,
                representation_repository, embedding_profile: str):
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
