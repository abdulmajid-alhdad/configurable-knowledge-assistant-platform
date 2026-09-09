"""Application-owned transaction phase contracts for source processing."""

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from knowledge_platform.application.knowledge_ingestion import (
    IngestionFailurePersistenceError,
    IngestionTransactionContext,
    KnowledgeSourceProcessingService,
    RepresentationRepositoryPort,
    SourceRepositoryPort,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
    KnowledgeSourceLifecycle,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


@dataclass
class Sources:
    current: KnowledgeSource
    transitions: int = 0

    def get(
        self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId
    ) -> KnowledgeSource | None:
        if self.current.id != source_id or self.current.workspace_id != workspace_id:
            return None
        return self.current

    def get_for_update(
        self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId
    ) -> KnowledgeSource | None:
        return self.get(source_id=source_id, workspace_id=workspace_id)

    def save_transition(
        self, *, previous: KnowledgeSource, transitioned: KnowledgeSource,
        workspace_id: WorkspaceId,
    ) -> None:
        self.current.validate_successor(transitioned)
        self.current = transitioned
        self.transitions += 1


class Representations:
    def __init__(self, versions: list[int] | None = None) -> None:
        self.versions = versions or []

    def add(self, representation: object) -> None:
        self.versions.append(getattr(representation, "version"))  # noqa: B009

    def activate(self, *, representation: object, workspace_id: WorkspaceId) -> None:
        pass

    def next_version(self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId) -> int:
        return max(self.versions, default=0) + 1


class Runner:
    def __init__(self, context: IngestionTransactionContext) -> None:
        self.context = context
        self.calls = 0
        self.fail_phase: int | None = None

    def run(
        self, workspace_id: WorkspaceId,
        operation: Callable[[IngestionTransactionContext], object],
    ) -> object:
        self.calls += 1
        if self.fail_phase == self.calls:
            raise RuntimeError("failure persistence unavailable")
        return operation(self.context)


class Ingestion:
    def __init__(self, *, fail: bool = False, artifact_available: bool = True) -> None:
        self.fail = fail
        self.artifact_available = artifact_available

    def original_artifact_exists(
        self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId
    ) -> bool:
        return self.artifact_available

    def process(
        self, *, workspace_id: WorkspaceId, source: KnowledgeSource,
        representation_repository: RepresentationRepositoryPort, embedding_profile: str,
        source_repository: SourceRepositoryPort,
        reindex: bool = False,
    ) -> KnowledgeSource:
        if self.fail:
            raise RuntimeError("processing failed")
        if reindex:
            class Representation:
                version = representation_repository.next_version(
                    source_id=source.id, workspace_id=workspace_id
                )

            representation_repository.add(Representation())
            representation_repository.activate(
                representation=Representation(), workspace_id=workspace_id
            )
            return source
        ready = source.mark_ready()
        source_repository.save_transition(
            previous=source, transitioned=ready, workspace_id=workspace_id
        )
        return ready


def _setup() -> tuple[WorkspaceId, KnowledgeSource, Runner, Sources]:
    workspace_id = WorkspaceId.new()
    source = KnowledgeSource.create(
        workspace_id=workspace_id, name="source", kind=KnowledgeSourceKind.DOCUMENT
    )
    sources = Sources(source)
    context = IngestionTransactionContext(sources, Representations())
    return workspace_id, source, Runner(context), sources


def test_processing_runs_prepare_and_process_phases_before_success() -> None:
    workspace_id, source, runner, sources = _setup()
    result = KnowledgeSourceProcessingService(
        transactions=runner, ingestion=Ingestion()
    ).process(
        workspace_id=workspace_id, source_id=source.id, embedding_profile="test"
    )

    assert result.lifecycle.value == "ready"
    assert sources.current.lifecycle.value == "ready"
    assert runner.calls == 2


def test_processing_failure_runs_failure_phase_and_preserves_original_error() -> None:
    workspace_id, source, runner, sources = _setup()

    with pytest.raises(RuntimeError, match="processing failed"):
        KnowledgeSourceProcessingService(
            transactions=runner, ingestion=Ingestion(fail=True)
        ).process(
            workspace_id=workspace_id, source_id=source.id, embedding_profile="test"
        )

    assert sources.current.lifecycle.value == "failed"
    assert sources.transitions == 2
    assert runner.calls == 3


def test_missing_original_does_not_change_processing_lifecycle() -> None:
    workspace_id, source, runner, sources = _setup()

    with pytest.raises(FileNotFoundError, match="original artifact is not stored"):
        KnowledgeSourceProcessingService(
            transactions=runner,
            ingestion=Ingestion(artifact_available=False),
        ).process(
            workspace_id=workspace_id,
            source_id=source.id,
            embedding_profile="test",
        )

    assert sources.current.lifecycle is KnowledgeSourceLifecycle.REGISTERED
    assert sources.transitions == 0
    assert runner.calls == 0


def test_failure_persistence_error_preserves_both_failures_without_success() -> None:
    workspace_id, source, runner, sources = _setup()
    runner.fail_phase = 3

    with pytest.raises(IngestionFailurePersistenceError) as caught:
        KnowledgeSourceProcessingService(
            transactions=runner, ingestion=Ingestion(fail=True)
        ).process(
            workspace_id=workspace_id, source_id=source.id, embedding_profile="test"
        )

    assert str(caught.value) == "ingestion failed and failure state could not be persisted"
    assert str(caught.value.processing_error) == "processing failed"
    assert str(caught.value.persistence_error) == "failure persistence unavailable"
    assert sources.current.lifecycle.value == "preparing"
    assert sources.transitions == 1


def _ready_setup() -> tuple[WorkspaceId, KnowledgeSource, Runner, Sources, Representations]:
    workspace_id = WorkspaceId.new()
    registered = KnowledgeSource.create(
        workspace_id=workspace_id, name="source", kind=KnowledgeSourceKind.DOCUMENT
    )
    preparing = registered.begin_preparation()
    ready = preparing.mark_ready()
    sources = Sources(ready)
    representations = Representations([1])
    runner = Runner(IngestionTransactionContext(sources, representations))
    return workspace_id, ready, runner, sources, representations


def test_ready_source_reindex_uses_next_version_and_stays_ready() -> None:
    workspace_id, source, runner, sources, representations = _ready_setup()
    result = KnowledgeSourceProcessingService(
        transactions=runner, ingestion=Ingestion()
    ).process(
        workspace_id=workspace_id, source_id=source.id, embedding_profile="test"
    )

    assert result.lifecycle is KnowledgeSourceLifecycle.READY
    assert sources.current.lifecycle is KnowledgeSourceLifecycle.READY
    assert representations.versions == [1, 2]
    assert runner.calls == 2


def test_ready_source_reindex_failure_preserves_ready_source_and_old_version() -> None:
    workspace_id, source, runner, sources, representations = _ready_setup()
    with pytest.raises(RuntimeError, match="processing failed"):
        KnowledgeSourceProcessingService(
            transactions=runner, ingestion=Ingestion(fail=True)
        ).process(
            workspace_id=workspace_id, source_id=source.id, embedding_profile="test"
        )

    assert sources.current.lifecycle is KnowledgeSourceLifecycle.READY
    assert representations.versions == [1]
    assert runner.calls == 2
