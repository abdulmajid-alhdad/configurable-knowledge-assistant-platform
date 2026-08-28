"""Immutable contracts for policy-bounded retrieval."""

from dataclasses import dataclass
from typing import Self

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


def _required_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized


def _source_ids(
    values: frozenset[KnowledgeSourceId], *, field: str
) -> frozenset[KnowledgeSourceId]:
    if not isinstance(values, frozenset):
        raise TypeError(f"{field} must be a frozenset")
    if not all(isinstance(value, KnowledgeSourceId) for value in values):
        raise TypeError(f"{field} must contain only KnowledgeSourceId values")
    return values


@dataclass(frozen=True, slots=True)
class EligibleSources:
    """The complete source set policy permits for one assistant request context."""

    workspace_id: WorkspaceId
    assistant_id: AssistantId
    source_ids: frozenset[KnowledgeSourceId]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        if not isinstance(self.assistant_id, AssistantId):
            raise TypeError("assistant_id must be an AssistantId")
        _source_ids(self.source_ids, field="source_ids")


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """A query and the policy-derived sources from which it may retrieve."""

    workspace_id: WorkspaceId
    assistant_id: AssistantId
    query: str
    eligible_sources: EligibleSources

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        if not isinstance(self.assistant_id, AssistantId):
            raise TypeError("assistant_id must be an AssistantId")
        if not isinstance(self.eligible_sources, EligibleSources):
            raise TypeError("eligible_sources must be EligibleSources")
        if self.eligible_sources.workspace_id != self.workspace_id:
            raise ValueError("eligible sources belong to a different workspace")
        if self.eligible_sources.assistant_id != self.assistant_id:
            raise ValueError("eligible sources belong to a different assistant")
        object.__setattr__(self, "query", _required_text(self.query, field="query"))


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """A policy-validated selection of sources for a retrieval request."""

    request: RetrievalRequest
    source_ids: frozenset[KnowledgeSourceId]

    def __post_init__(self) -> None:
        if not isinstance(self.request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        _source_ids(self.source_ids, field="source_ids")
        denied = self.source_ids - self.request.eligible_sources.source_ids
        if denied:
            raise ValueError("retrieval plan contains a source not eligible under policy")

    @classmethod
    def all_eligible(cls, request: RetrievalRequest) -> Self:
        """Plan retrieval from every policy-eligible source."""
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        return cls(request=request, source_ids=request.eligible_sources.source_ids)


@dataclass(frozen=True, slots=True)
class RetrievedContent:
    """Untrusted source data; it conveys no policy, authority, or authorization."""

    source_id: KnowledgeSourceId
    content: str
    provenance_locator: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, KnowledgeSourceId):
            raise TypeError("source_id must be a KnowledgeSourceId")
        object.__setattr__(self, "content", _required_text(self.content, field="content"))
        object.__setattr__(
            self,
            "provenance_locator",
            _required_text(self.provenance_locator, field="provenance_locator"),
        )


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Untrusted content returned for a validated retrieval plan."""

    plan: RetrievalPlan
    items: tuple[RetrievedContent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RetrievalPlan):
            raise TypeError("plan must be a RetrievalPlan")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if not all(isinstance(item, RetrievedContent) for item in self.items):
            raise TypeError("items must contain only RetrievedContent values")
        if any(item.source_id not in self.plan.source_ids for item in self.items):
            raise ValueError("retrieval result contains content from an unplanned source")
