"""Safe structured retrieval orchestration."""

from typing import Any

from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    Evidence,
    GroundingOutcome,
    PolicyDenied,
    TechnicalFailure,
    grounding_outcome,
)
from knowledge_platform.modules.structured_retrieval.contracts import (
    StructuredPlannerPort,
    StructuredSourcePolicy,
    result_from_rows,
)
from knowledge_platform.modules.structured_retrieval.validation import (
    PolicyDeniedError,
    validate_plan,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


class StructuredRetrievalService:
    def __init__(self, *, planner: StructuredPlannerPort, executor: Any) -> None:
        self._planner, self._executor = planner, executor

    def ask(self, *, question: str, workspace_id: WorkspaceId, assistant_id: AssistantId,
             policy: StructuredSourcePolicy, metadata: tuple[Any, ...]) -> GroundingOutcome:
        try:
            plan = self._planner.plan(question=question, metadata=metadata)
            if policy.workspace_id != workspace_id:
                raise PolicyDeniedError("source workspace is not authorized")
            validated = validate_plan(plan, policy)
            rows = self._executor.execute(validated)
            result = result_from_rows(plan=validated, rows=tuple(rows), assistant_id=assistant_id)
            evidence = tuple(
                Evidence(
                    source_id=item.source_id,
                    content=item.content,
                    provenance_locator=item.provenance_locator,
                )
                for item in result.items
            )
            return grounding_outcome(answer="Structured result", evidence=evidence)
        except PolicyDeniedError as exc:
            return PolicyDenied(reason=str(exc))
        except Exception as exc:
            return TechnicalFailure(reason=str(exc) or "structured retrieval failed")
