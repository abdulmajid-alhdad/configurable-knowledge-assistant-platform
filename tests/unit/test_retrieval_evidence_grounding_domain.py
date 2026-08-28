"""Focused tests for retrieval, evidence, and grounding contracts."""

from dataclasses import FrozenInstanceError, fields
from typing import cast

import pytest

from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    Evidence,
    GroundedAnswer,
    GroundingDecision,
    InsufficientEvidence,
    PolicyDenied,
    TechnicalFailure,
    grounding_outcome,
)
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


def request(*source_ids: KnowledgeSourceId) -> RetrievalRequest:
    workspace_id = WorkspaceId.new()
    assistant_id = AssistantId.new()
    return RetrievalRequest(
        workspace_id=workspace_id,
        assistant_id=assistant_id,
        query=" What is supported? ",
        eligible_sources=EligibleSources(
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            source_ids=frozenset(source_ids),
        ),
    )


def test_request_reuses_typed_identities_and_normalizes_query() -> None:
    source_id = KnowledgeSourceId.new()
    retrieval_request = request(source_id)

    assert retrieval_request.query == "What is supported?"
    assert retrieval_request.eligible_sources.source_ids == frozenset({source_id})
    assert {field.name for field in fields(RetrievalRequest)} == {
        "workspace_id", "assistant_id", "query", "eligible_sources"
    }


def test_request_rejects_mismatched_policy_context() -> None:
    retrieval_request = request()
    with pytest.raises(ValueError, match="different workspace"):
        RetrievalRequest(
            workspace_id=WorkspaceId.new(),
            assistant_id=retrieval_request.assistant_id,
            query="query",
            eligible_sources=retrieval_request.eligible_sources,
        )


def test_plan_accepts_only_policy_eligible_sources() -> None:
    eligible = KnowledgeSourceId.new()
    denied = KnowledgeSourceId.new()
    retrieval_request = request(eligible)

    plan = RetrievalPlan(request=retrieval_request, source_ids=frozenset({eligible}))
    assert plan.source_ids == frozenset({eligible})
    with pytest.raises(ValueError, match="not eligible under policy"):
        RetrievalPlan(request=retrieval_request, source_ids=frozenset({denied}))


def test_empty_eligibility_and_empty_plan_are_explicit_and_valid() -> None:
    retrieval_request = request()
    plan = RetrievalPlan.all_eligible(retrieval_request)
    assert plan.source_ids == frozenset()


def test_result_rejects_content_from_an_unplanned_source() -> None:
    planned = KnowledgeSourceId.new()
    plan = RetrievalPlan.all_eligible(request(planned))
    item = RetrievedContent(
        source_id=planned,
        content=" Untrusted retrieved text ",
        provenance_locator=" opaque-locator ",
    )
    result = RetrievalResult(plan=plan, items=(item,))

    assert result.items[0].content == "Untrusted retrieved text"
    assert result.items[0].provenance_locator == "opaque-locator"
    with pytest.raises(ValueError, match="unplanned source"):
        RetrievalResult(
            plan=plan,
            items=(
                RetrievedContent(
                    source_id=KnowledgeSourceId.new(),
                    content="text",
                    provenance_locator="locator",
                ),
            ),
        )


def test_evidence_and_grounded_answer_require_nonblank_content() -> None:
    evidence = Evidence(
        source_id=KnowledgeSourceId.new(),
        content=" Support ",
        provenance_locator=" location ",
    )
    outcome = GroundedAnswer(answer=" Answer ", evidence=(evidence,))

    assert outcome.answer == "Answer"
    assert outcome.evidence == (evidence,)
    assert outcome.decision is GroundingDecision.SUFFICIENT
    with pytest.raises(ValueError, match="answer must not be blank"):
        GroundedAnswer(answer=" ", evidence=(evidence,))


def test_zero_evidence_yields_insufficient_evidence() -> None:
    outcome = grounding_outcome(answer="would otherwise be an answer", evidence=())

    assert isinstance(outcome, InsufficientEvidence)
    assert outcome.decision is GroundingDecision.INSUFFICIENT
    with pytest.raises(ValueError, match="at least one Evidence"):
        GroundedAnswer(answer="answer", evidence=())


def test_grounding_decision_values_are_exact() -> None:
    assert set(GroundingDecision) == {
        GroundingDecision.SUFFICIENT,
        GroundingDecision.INSUFFICIENT,
    }


@pytest.mark.parametrize("outcome_type", [PolicyDenied, TechnicalFailure])
def test_non_grounding_terminal_outcomes_require_a_reason(
    outcome_type: type[PolicyDenied] | type[TechnicalFailure],
) -> None:
    assert outcome_type(reason=" denied ").reason == "denied"
    with pytest.raises(ValueError, match="reason must not be blank"):
        outcome_type(reason=" ")


def test_contracts_are_frozen_slotted_and_runtime_typed() -> None:
    retrieval_request = request()
    with pytest.raises(FrozenInstanceError):
        retrieval_request.__setattr__("query", "changed")
    with pytest.raises(TypeError, match="source_ids must be a frozenset"):
        EligibleSources(
            workspace_id=retrieval_request.workspace_id,
            assistant_id=retrieval_request.assistant_id,
            source_ids=cast(frozenset[KnowledgeSourceId], set()),
        )
    assert not hasattr(retrieval_request, "__dict__")


def test_contracts_have_no_provider_or_implementation_fields() -> None:
    all_fields = {
        field.name
        for contract in (
            EligibleSources, RetrievalRequest, RetrievalPlan, RetrievedContent,
            RetrievalResult, Evidence, GroundedAnswer, InsufficientEvidence,
            PolicyDenied, TechnicalFailure,
        )
        for field in fields(contract)
    }
    assert all_fields.isdisjoint(
        {"provider", "model", "embedding", "vector", "http", "table", "credential"}
    )
