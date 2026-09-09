"""Product-level upload and reprocessing orchestration."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from knowledge_platform.application.document_ingestion import DocumentIngestionService
from knowledge_platform.modules.document_knowledge.artifacts import (
    OriginalArtifact,
    OriginalArtifactStorePort,
)
from knowledge_platform.modules.document_knowledge.ports import DocumentParserPort
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceLifecycle
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class SourceRepositoryPort(Protocol):
    def get(
        self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId
    ) -> KnowledgeSource | None: ...
    def get_for_update(
        self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId
    ) -> KnowledgeSource | None: ...

    def save_transition(self, *, previous: KnowledgeSource, transitioned: KnowledgeSource,
                        workspace_id: WorkspaceId) -> None: ...


class RepresentationRepositoryPort(Protocol):
    def add(self, representation: Any) -> None: ...
    def activate(self, *, representation: Any, workspace_id: WorkspaceId) -> None: ...
    def next_version(self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId) -> int: ...


@dataclass(frozen=True, slots=True)
class IngestionTransactionContext:
    source_repository: SourceRepositoryPort
    representation_repository: RepresentationRepositoryPort


T = TypeVar("T")


class WorkspaceTransactionPort(Protocol):
    def run(
        self,
        workspace_id: WorkspaceId,
        operation: Callable[[IngestionTransactionContext], T],
    ) -> T: ...


class IngestionProcessPort(Protocol):
    def original_artifact_exists(
        self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId
    ) -> bool: ...

    def process(
        self,
        *,
        workspace_id: WorkspaceId,
        source: KnowledgeSource,
        representation_repository: RepresentationRepositoryPort,
        embedding_profile: str,
        source_repository: SourceRepositoryPort,
        reindex: bool = False,
    ) -> KnowledgeSource: ...


class IngestionFailurePersistenceError(RuntimeError):
    """Processing and durable FAILED persistence both failed."""

    def __init__(self, processing_error: Exception, persistence_error: Exception) -> None:
        super().__init__("ingestion failed and failure state could not be persisted")
        self.processing_error = processing_error
        self.persistence_error = persistence_error


class SourceProcessingPort(Protocol):
    def process(
        self,
        *,
        workspace_id: WorkspaceId,
        source_id: KnowledgeSourceId,
        embedding_profile: str,
    ) -> KnowledgeSource: ...


class KnowledgeSourceProcessingService:
    """Owns the application-level transaction phases for source processing."""

    def __init__(
        self,
        *,
        transactions: WorkspaceTransactionPort,
        ingestion: IngestionProcessPort,
    ) -> None:
        self._transactions = transactions
        self._ingestion = ingestion

    def process(
        self,
        *,
        workspace_id: WorkspaceId,
        source_id: KnowledgeSourceId,
        embedding_profile: str,
    ) -> KnowledgeSource:
        if not self._ingestion.original_artifact_exists(
            workspace_id=workspace_id, source_id=source_id
        ):
            raise FileNotFoundError("original artifact is not stored")

        def prepare(context: IngestionTransactionContext) -> KnowledgeSource:
            source = context.source_repository.get(
                source_id=source_id, workspace_id=workspace_id
            )
            if source is None:
                raise LookupError("source not found")
            if source.lifecycle is KnowledgeSourceLifecycle.READY:
                return source
            preparing = source.begin_preparation()
            context.source_repository.save_transition(
                previous=source, transitioned=preparing, workspace_id=workspace_id
            )
            return preparing

        current = self._transactions.run(workspace_id, prepare)
        if current.lifecycle is KnowledgeSourceLifecycle.READY:
            def reindex(context: IngestionTransactionContext) -> KnowledgeSource:
                source = context.source_repository.get_for_update(
                    source_id=source_id, workspace_id=workspace_id
                )
                if source is None:
                    raise LookupError("source not found")
                return self._ingestion.process(
                    workspace_id=workspace_id,
                    source=source,
                    source_repository=context.source_repository,
                    representation_repository=context.representation_repository,
                    embedding_profile=embedding_profile,
                    reindex=True,
                )

            return self._transactions.run(workspace_id, reindex)

        def process(context: IngestionTransactionContext) -> KnowledgeSource:
            source = context.source_repository.get(
                source_id=source_id, workspace_id=workspace_id
            )
            if source is None:
                raise LookupError("source not found")
            return self._ingestion.process(
                workspace_id=workspace_id,
                source=source,
                source_repository=context.source_repository,
                representation_repository=context.representation_repository,
                embedding_profile=embedding_profile,
            )

        try:
            return self._transactions.run(workspace_id, process)
        except Exception as processing_error:
            def fail(context: IngestionTransactionContext) -> None:
                source = context.source_repository.get(
                    source_id=source_id, workspace_id=workspace_id
                )
                if source is None:
                    raise LookupError("source not found")
                if source.lifecycle is not KnowledgeSourceLifecycle.PREPARING:
                    return
                failed = source.mark_failed()
                context.source_repository.save_transition(
                    previous=source, transitioned=failed, workspace_id=workspace_id
                )

            try:
                self._transactions.run(workspace_id, fail)
            except Exception as persistence_error:
                raise IngestionFailurePersistenceError(
                    processing_error, persistence_error
                ) from processing_error
            raise


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

    def original_artifact_exists(
        self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId
    ) -> bool:
        return self._artifacts.exists(
            workspace_id=workspace_id, source_id=source_id
        )

    def process(self, *, workspace_id: WorkspaceId, source: KnowledgeSource,
                representation_repository: RepresentationRepositoryPort,
                embedding_profile: str, source_repository: SourceRepositoryPort,
                reindex: bool = False) -> KnowledgeSource:
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
            reindex=reindex,
        )
