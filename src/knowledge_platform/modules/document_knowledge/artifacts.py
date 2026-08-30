"""Port for durable original knowledge artifacts."""
# ruff: noqa: E501

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


@dataclass(frozen=True, slots=True)
class OriginalArtifact:
    workspace_id: WorkspaceId
    source_id: KnowledgeSourceId
    original_filename: str
    suffix: str
    media_type: str | None
    byte_size: int
    sha256: str


class OriginalArtifactStorePort(Protocol):
    def store(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId,
              chunks: Iterable[bytes], filename: str, media_type: str | None,
              max_bytes: int) -> OriginalArtifact: ...
    def retrieve(self, artifact: OriginalArtifact) -> bytes: ...
    def get(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> OriginalArtifact | None: ...
    def exists(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> bool: ...
