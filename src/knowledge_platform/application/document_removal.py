"""Application-owned KnowledgeSource removal flow."""

from typing import Any

from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class DocumentRemovalService:
    """Retire searchable representations before completing source removal."""

    def remove(
        self,
        *,
        source: KnowledgeSource,
        source_repository: Any,
        representation_repository: Any,
        workspace_id: WorkspaceId,
    ) -> KnowledgeSource:
        if source.workspace_id != workspace_id:
            raise ValueError("knowledge source workspace does not match persistence workspace")
        removing = source.begin_removal()
        source_repository.save_transition(
            previous=source, transitioned=removing, workspace_id=workspace_id
        )
        representation_repository.retire_active_for_source(
            source_id=source.id, workspace_id=workspace_id
        )
        removed = removing.mark_removed()
        source_repository.save_transition(
            previous=removing, transitioned=removed, workspace_id=workspace_id
        )
        return removed
