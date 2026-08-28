"""Explicit assistant access to knowledge sources."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

from .identifiers import KnowledgeSourceId
from .knowledge_source import KnowledgeSource


@dataclass(frozen=True, slots=True)
class KnowledgeAccessScope:
    """The complete explicit source set available to one assistant."""

    assistant_id: AssistantId
    workspace_id: WorkspaceId
    source_ids: frozenset[KnowledgeSourceId]

    def __post_init__(self) -> None:
        if not isinstance(self.assistant_id, AssistantId):
            raise TypeError("assistant_id must be an AssistantId")
        if not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        if not isinstance(self.source_ids, frozenset):
            raise TypeError("source_ids must be a frozenset")
        if not all(isinstance(source_id, KnowledgeSourceId) for source_id in self.source_ids):
            raise TypeError("source_ids must contain only KnowledgeSourceId values")

    @classmethod
    def for_assistant(
        cls,
        *,
        assistant: Assistant,
        sources: Iterable[KnowledgeSource],
    ) -> Self:
        """Create an explicit access scope from same-workspace sources."""
        if not isinstance(assistant, Assistant):
            raise TypeError("assistant must be an Assistant")
        source_ids = _validated_source_ids(sources, workspace_id=assistant.workspace_id)
        return cls(
            assistant_id=assistant.id,
            workspace_id=assistant.workspace_id,
            source_ids=source_ids,
        )

    def replace_sources(
        self,
        *,
        assistant: Assistant,
        sources: Iterable[KnowledgeSource],
    ) -> Self:
        """Replace the complete source set without changing scope ownership."""
        if not isinstance(assistant, Assistant):
            raise TypeError("assistant must be an Assistant")
        if assistant.id != self.assistant_id:
            raise ValueError("assistant identity does not match this access scope")
        if assistant.workspace_id != self.workspace_id:
            raise ValueError("assistant workspace does not match this access scope")
        return type(self)(
            assistant_id=self.assistant_id,
            workspace_id=self.workspace_id,
            source_ids=_validated_source_ids(sources, workspace_id=self.workspace_id),
        )

    def allows(self, source: KnowledgeSource) -> bool:
        """Return whether a same-workspace source is explicitly selected."""
        if not isinstance(source, KnowledgeSource):
            raise TypeError("source must be a KnowledgeSource")
        return source.workspace_id == self.workspace_id and source.id in self.source_ids


def _validated_source_ids(
    sources: Iterable[KnowledgeSource],
    *,
    workspace_id: WorkspaceId,
) -> frozenset[KnowledgeSourceId]:
    source_ids: set[KnowledgeSourceId] = set()
    for source in sources:
        if not isinstance(source, KnowledgeSource):
            raise TypeError("sources must contain only KnowledgeSource values")
        if source.workspace_id != workspace_id:
            raise ValueError("knowledge source belongs to a different workspace")
        source_ids.add(source.id)
    return frozenset(source_ids)
