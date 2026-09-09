"""Deliberate provisioning recipe for the Yemen reference configuration."""
from collections.abc import Iterable
from typing import Protocol

from knowledge_platform.application.assistant_knowledge_scope import AssistantKnowledgeScopeService
from knowledge_platform.application.assistants import AssistantService
from knowledge_platform.application.knowledge_ingestion import SourceProcessingPort
from knowledge_platform.application.knowledge_sources import KnowledgeSourceService
from knowledge_platform.application.workspaces import WorkspaceService
from knowledge_platform.modules.document_knowledge.artifacts import OriginalArtifact
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

from .manifest import DEFINITION, artifact_path


class ArtifactStorePort(Protocol):
    def store(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId,
              chunks: Iterable[bytes], filename: str, media_type: str | None,
              max_bytes: int) -> OriginalArtifact: ...

class YemenHistoryReferenceProvisioner:
    """Explicit, caller-invoked setup; never used during normal startup."""

    def __init__(self, *, workspaces: WorkspaceService, assistants: AssistantService,
                 sources: KnowledgeSourceService, artifacts: ArtifactStorePort,
                 processing: SourceProcessingPort,
                 scope: AssistantKnowledgeScopeService,
                 embedding_profile: str = "reference") -> None:
        self._workspaces, self._assistants, self._sources = workspaces, assistants, sources
        self._artifacts, self._processing, self._scope = artifacts, processing, scope
        self._embedding_profile = embedding_profile

    def provision(self) -> tuple[object, object, object]:
        workspace = self._workspaces.create(name=DEFINITION.workspace_name)
        assistant = self._assistants.create(
            workspace_id=workspace.id, name=DEFINITION.assistant_name,
            description="Arabic grounded history reference",
            instructions=DEFINITION.assistant_instructions, language="ar",
            provider="remote", model_reference="configured",
        )
        source = self._sources.register(
            workspace_id=workspace.id, name=DEFINITION.source_name,
            kind=KnowledgeSourceKind.DOCUMENT,
        )
        artifact = artifact_path().read_bytes()
        self._artifacts.store(
            workspace_id=workspace.id, source_id=source.id, chunks=(artifact,),
            filename=DEFINITION.artifact_name, media_type="text/markdown", max_bytes=len(artifact),
        )
        with_source = self._processing.process(
            workspace_id=workspace.id,
            source_id=source.id,
            embedding_profile=self._embedding_profile,
        )
        self._scope.attach(
            workspace_id=workspace.id, assistant_id=assistant.id, source_id=source.id
        )
        return workspace, assistant, with_source
