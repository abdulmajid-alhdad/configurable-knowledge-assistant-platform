"""Typed, non-executable contracts for safe structured retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.retrieval_orchestration.domain.contracts import (
    EligibleSources,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalResult,
    RetrievedContent,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)

type Scalar = str | int | float | bool | None

@dataclass(frozen=True, slots=True)
class StructuredSourcePolicy:
    source_id: KnowledgeSourceId
    workspace_id: WorkspaceId
    engine: Literal["postgresql", "sqlite"]
    allowed_schema: str
    allowed_relations: frozenset[str]
    allowed_columns: dict[str, frozenset[str]]
    restricted_columns: frozenset[str] = frozenset()
    max_rows: int = 100

@dataclass(frozen=True, slots=True)
class StructuredQueryPlan:
    source_id: KnowledgeSourceId
    relation: str
    fields: tuple[str, ...]
    filters: tuple[tuple[str, str, Scalar], ...] = ()
    order_by: tuple[str, ...] = ()
    limit: int = 50

@dataclass(frozen=True, slots=True)
class ValidatedStructuredPlan:
    plan: StructuredQueryPlan
    policy: StructuredSourcePolicy


class StructuredPlannerPort(Protocol):
    def plan(
        self, *, question: str, metadata: tuple[RelationMetadata, ...]
    ) -> StructuredQueryPlan: ...


@dataclass(frozen=True, slots=True)
class RelationMetadata:
    schema: str
    relation: str
    columns: tuple[str, ...]


def result_from_rows(
    *, plan: ValidatedStructuredPlan, rows: tuple[dict[str, object], ...], assistant_id: AssistantId
) -> RetrievalResult:
    request = RetrievalRequest(
        workspace_id=plan.policy.workspace_id,
        assistant_id=assistant_id,
        query=plan.plan.relation,
        eligible_sources=EligibleSources(
            workspace_id=plan.policy.workspace_id,
            assistant_id=assistant_id,
            source_ids=frozenset({plan.policy.source_id}),
        ),
    )
    # Keep source identity and only validated fields; row rendering is bounded by the adapter.
    items = tuple(
        RetrievedContent(
            source_id=plan.policy.source_id,
            content=" ".join(f"{field}={row[field]}" for field in plan.plan.fields),
            provenance_locator=f"{plan.policy.allowed_schema}.{plan.plan.relation}",
        )
        for row in rows
    )
    return RetrievalResult(plan=RetrievalPlan.all_eligible(request), items=items)
