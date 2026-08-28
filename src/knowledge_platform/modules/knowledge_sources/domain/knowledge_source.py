"""Knowledge source aggregate root."""

from dataclasses import dataclass, replace
from typing import Self

from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

from ._validation import required_text
from .identifiers import KnowledgeSourceId
from .lifecycle import KnowledgeSourceKind, KnowledgeSourceLifecycle


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    """A workspace-owned source with an administrative lifecycle."""

    id: KnowledgeSourceId
    workspace_id: WorkspaceId
    name: str
    kind: KnowledgeSourceKind
    lifecycle: KnowledgeSourceLifecycle

    def __post_init__(self) -> None:
        if not isinstance(self.id, KnowledgeSourceId):
            raise TypeError("id must be a KnowledgeSourceId")
        if not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        if not isinstance(self.kind, KnowledgeSourceKind):
            raise TypeError("kind must be a KnowledgeSourceKind")
        if not isinstance(self.lifecycle, KnowledgeSourceLifecycle):
            raise TypeError("lifecycle must be a KnowledgeSourceLifecycle")
        object.__setattr__(self, "name", required_text(self.name, field="name"))

    @classmethod
    def create(
        cls,
        *,
        workspace_id: WorkspaceId,
        name: str,
        kind: KnowledgeSourceKind,
    ) -> Self:
        """Create a registered knowledge source with a generated identity."""
        return cls(
            id=KnowledgeSourceId.new(),
            workspace_id=workspace_id,
            name=name,
            kind=kind,
            lifecycle=KnowledgeSourceLifecycle.REGISTERED,
        )

    def begin_preparation(self) -> Self:
        """Begin preparing a registered or previously failed source."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.REGISTERED, KnowledgeSourceLifecycle.FAILED),
            target=KnowledgeSourceLifecycle.PREPARING,
            operation="begin_preparation",
        )

    def mark_ready(self) -> Self:
        """Mark a source ready after preparation completes."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.PREPARING,),
            target=KnowledgeSourceLifecycle.READY,
            operation="mark_ready",
        )

    def mark_failed(self) -> Self:
        """Mark preparation as failed."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.PREPARING,),
            target=KnowledgeSourceLifecycle.FAILED,
            operation="mark_failed",
        )

    def disable(self) -> Self:
        """Disable a ready source."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.READY,),
            target=KnowledgeSourceLifecycle.DISABLED,
            operation="disable",
        )

    def enable(self) -> Self:
        """Re-enable a disabled source."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.DISABLED,),
            target=KnowledgeSourceLifecycle.READY,
            operation="enable",
        )

    def begin_removal(self) -> Self:
        """Begin removing a ready or disabled source."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.READY, KnowledgeSourceLifecycle.DISABLED),
            target=KnowledgeSourceLifecycle.REMOVING,
            operation="begin_removal",
        )

    def mark_removed(self) -> Self:
        """Complete removal after removal begins."""
        return self._transition(
            allowed_from=(KnowledgeSourceLifecycle.REMOVING,),
            target=KnowledgeSourceLifecycle.REMOVED,
            operation="mark_removed",
        )

    def _transition(
        self,
        *,
        allowed_from: tuple[KnowledgeSourceLifecycle, ...],
        target: KnowledgeSourceLifecycle,
        operation: str,
    ) -> Self:
        if self.lifecycle not in allowed_from:
            raise ValueError(f"{operation} is invalid from {self.lifecycle.value}")
        return replace(self, lifecycle=target)

    @property
    def is_retrieval_eligible(self) -> bool:
        return self.lifecycle is KnowledgeSourceLifecycle.READY

    def rename(self, *, name: str) -> Self:
        """Return a validated replacement with a new name."""
        return replace(self, name=name)
