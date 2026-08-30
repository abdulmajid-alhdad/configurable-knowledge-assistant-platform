from dataclasses import replace

from knowledge_platform.application.document_removal import DocumentRemovalService
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
    KnowledgeSourceLifecycle,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


def test_document_removal_retires_active_representation_before_removed() -> None:
    workspace_id = WorkspaceId.new()
    source = KnowledgeSource.create(
        workspace_id=workspace_id, name="demo", kind=KnowledgeSourceKind.DOCUMENT
    )
    source = replace(source, lifecycle=KnowledgeSourceLifecycle.READY)
    transitions: list[KnowledgeSourceLifecycle] = []

    class SourceRepository:
        def save_transition(
            self, *, previous: KnowledgeSource, transitioned: KnowledgeSource,
            workspace_id: WorkspaceId,
        ) -> None:
            assert previous.workspace_id == workspace_id
            previous.validate_successor(transitioned)
            transitions.append(transitioned.lifecycle)

    class RepresentationRepository:
        retired = False

        def retire_active_for_source(
            self, *, source_id: KnowledgeSourceId, workspace_id: WorkspaceId,
        ) -> None:
            assert source_id == source.id
            assert workspace_id == source.workspace_id
            self.retired = True

    representations = RepresentationRepository()
    removed = DocumentRemovalService().remove(
        source=source,
        source_repository=SourceRepository(),
        representation_repository=representations,
        workspace_id=workspace_id,
    )
    assert transitions == [
        KnowledgeSourceLifecycle.REMOVING,
        KnowledgeSourceLifecycle.REMOVED,
    ]
    assert representations.retired is True
    assert removed.lifecycle is KnowledgeSourceLifecycle.REMOVED
