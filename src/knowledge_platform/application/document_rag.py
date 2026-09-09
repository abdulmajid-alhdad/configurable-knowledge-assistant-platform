"""Small complete Document RAG orchestration using provider-neutral ports."""

import logging
from typing import Any

from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.message import (
    MessageEvidence,
    MessageOutcome,
)
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.document_knowledge.ports import (
    EmbeddingGatewayPort,
    GroundedModelAnswer,
    ModelInsufficientEvidence,
    ModelPort,
    VectorSearchPort,
)
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    Evidence,
    GroundedAnswer,
    GroundingOutcome,
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
from knowledge_platform.modules.workspace_assistant.domain.security import (
    DataEgressPolicy,
    PolicyDecision,
    ProcessingLocation,
)

logger = logging.getLogger(__name__)


class DatabaseRetrievalFailure(RuntimeError):
    """Safe retrieval failure metadata without retaining a DBAPI exception."""

    def __init__(
        self,
        *,
        sqlstate: str | None = None,
        constraint_name: str | None = None,
        table_name: str | None = None,
        schema_name: str | None = None,
    ) -> None:
        super().__init__("database retrieval failed")
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name
        self.table_name = table_name
        self.schema_name = schema_name


def _database_diagnostics(error: Exception) -> dict[str, str]:
    diagnostics: dict[str, str] = {}
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for field in ("sqlstate", "constraint_name", "table_name", "schema_name"):
            value = getattr(current, field, None)
            if isinstance(value, str) and value:
                diagnostics.setdefault(field, value)
        diag = getattr(current, "diag", None)
        if diag is None:
            original = getattr(current, "orig", None)
            diag = getattr(original, "diag", None)
        if diag is not None:
            for field, key in (
                ("sqlstate", "sqlstate"),
                ("constraint_name", "constraint_name"),
                ("table_name", "table_name"),
                ("schema_name", "schema_name"),
            ):
                value = getattr(diag, field, None)
                if isinstance(value, str) and value:
                    diagnostics.setdefault(key, value)
        current = current.__cause__ or current.__context__
    return diagnostics


def _log_database_failure(*, workspace_id: WorkspaceId, error: Exception) -> None:
    diagnostics = _database_diagnostics(error)
    rendered = " ".join(
        f"{field}={diagnostics.get(field, 'unknown')}"
        for field in ("sqlstate", "constraint_name", "table_name", "schema_name")
    )
    logger.error(
        "rag_database_operation_failed workspace_id=%s %s exception_type=%s",
        workspace_id,
        rendered,
        type(error).__name__,
    )


def _log_rag_failure(*, workspace_id: WorkspaceId, stage: str, error: Exception) -> None:
    logger.error(
        "rag_operation_failed workspace_id=%s stage=%s exception_type=%s",
        workspace_id,
        stage,
        type(error).__name__,
    )


class DocumentRagService:
    def __init__(
        self,
        *,
        embeddings: EmbeddingGatewayPort,
        vectors: VectorSearchPort,
        model: ModelPort,
        egress: DataEgressPolicy,
        max_retrieval_distance: float = 0.4,
    ) -> None:
        if max_retrieval_distance < 0:
            raise ValueError("max_retrieval_distance must not be negative")
        self.embeddings, self.vectors, self.model, self.egress = embeddings, vectors, model, egress
        self.max_retrieval_distance = max_retrieval_distance

    def ask(
        self,
        *,
        workspace_id: WorkspaceId,
        assistant_id: AssistantId,
        question: str,
        source_ids: frozenset[KnowledgeSourceId],
        private_data: bool = True,
        assistant_instructions: str | None = None,
    ) -> GroundingOutcome:
        request = RetrievalRequest(
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            query=question,
            eligible_sources=EligibleSources(
                workspace_id=workspace_id, assistant_id=assistant_id, source_ids=source_ids
            ),
        )
        plan = RetrievalPlan.all_eligible(request)
        if not plan.source_ids:
            return grounding_outcome(answer="", evidence=())
        if (
            self.egress.decide(
                processing_location=ProcessingLocation.EXTERNAL,
                contains_private_data=private_data,
            )
            is PolicyDecision.DENY
        ):
            return PolicyDenied(reason="external private-data egress denied")
        try:
            query_vector = self.embeddings.embed_query(question)
        except Exception as exc:
            _log_rag_failure(workspace_id=workspace_id, stage="query_embedding", error=exc)
            return TechnicalFailure(reason="document RAG failed")
        try:
            found: tuple[Any, ...] = self.vectors.search(
                workspace_id=workspace_id, source_ids=plan.source_ids, query=query_vector
            )
        except DatabaseRetrievalFailure as exc:
            _log_database_failure(workspace_id=workspace_id, error=exc)
            raise
        except Exception as exc:
            _log_rag_failure(workspace_id=workspace_id, stage="retrieval", error=exc)
            return TechnicalFailure(reason="document RAG failed")
        try:
            result = RetrievalResult(
                plan=plan,
                items=tuple(
                    RetrievedContent(
                        source_id=c.source_id,
                        content=c.content,
                        provenance_locator=c.provenance_locator,
                        distance=getattr(c, "distance", None),
                    )
                    for c in found
                ),
            )
            evidence = tuple(
                Evidence(
                    source_id=i.source_id,
                    content=i.content,
                    provenance_locator=i.provenance_locator,
                )
                for i in result.items
                if i.distance is None or i.distance <= self.max_retrieval_distance
            )
        except Exception as exc:
            _log_rag_failure(workspace_id=workspace_id, stage="evidence_mapping", error=exc)
            return TechnicalFailure(reason="document RAG failed")
        if not evidence:
            return grounding_outcome(answer="", evidence=())
        evidence_context = "\n".join(
            f"E{index}: {item.content}" for index, item in enumerate(evidence, start=1)
        )
        normalized_instructions = (
            assistant_instructions.strip()
            if isinstance(assistant_instructions, str) and assistant_instructions.strip()
            else None
        )
        try:
            context = (
                "Answer only from the supplied evidence. Do not use general or external "
                "knowledge; if the evidence does not support the question, say so.\n\n"
                "Evidence:\n"
                + evidence_context
            )
            if normalized_instructions is None:
                generated = self.model.generate(question=question, context=context)
            else:
                generated = self.model.generate(
                    question=question,
                    context=context,
                    assistant_instructions=normalized_instructions,
                )
        except Exception as exc:
            _log_rag_failure(workspace_id=workspace_id, stage="model_generation", error=exc)
            return TechnicalFailure(reason="document RAG failed")
        try:
            if isinstance(generated, ModelInsufficientEvidence):
                return InsufficientEvidence(reason="no evidence supports an answer")
            if not isinstance(generated, GroundedModelAnswer):
                raise TypeError("model returned an unsupported result")
            evidence_by_id = {
                f"E{index}": item for index, item in enumerate(evidence, start=1)
            }
            cited_ids = generated.evidence_ids
            if len(set(cited_ids)) != len(cited_ids) or any(
                evidence_id not in evidence_by_id for evidence_id in cited_ids
            ):
                raise ValueError("model cited unknown evidence")
            cited_evidence = tuple(evidence_by_id[evidence_id] for evidence_id in cited_ids)
            return grounding_outcome(answer=generated.answer, evidence=cited_evidence)
        except Exception as exc:
            _log_rag_failure(workspace_id=workspace_id, stage="model_response", error=exc)
            return TechnicalFailure(reason="document RAG failed")

    def ask_in_conversation(
        self, *, conversation: Conversation, workspace_id: WorkspaceId,
        assistant_id: AssistantId, question: str, source_ids: frozenset[KnowledgeSourceId],
        assistant_instructions: str | None = None,
        conversation_repository: Any, message_repository: Any,
    ) -> GroundingOutcome:
        """Append question and textual outcome through the existing append-only repositories."""
        if conversation.workspace_id != workspace_id:
            raise ValueError("conversation workspace does not match request")
        if conversation.assistant_id != assistant_id:
            raise ValueError("conversation assistant does not match request")
        with_question = conversation.append_message(role=MessageRole.USER, content=question)
        message_repository.add(with_question, workspace_id=workspace_id)
        outcome = self.ask(
            workspace_id=workspace_id, assistant_id=assistant_id, question=question,
            source_ids=source_ids, assistant_instructions=assistant_instructions,
        )
        if isinstance(outcome, GroundedAnswer):
            answer = outcome.answer
            persisted_outcome = MessageOutcome.GROUNDED
            persisted_evidence = tuple(
                MessageEvidence(
                    source_id=item.source_id,
                    content=item.content,
                    provenance_locator=item.provenance_locator,
                )
                for item in outcome.evidence
            )
        elif isinstance(outcome, InsufficientEvidence):
            answer = outcome.reason
            persisted_outcome = MessageOutcome.INSUFFICIENT_EVIDENCE
            persisted_evidence = ()
        elif isinstance(outcome, PolicyDenied):
            answer = outcome.reason
            persisted_outcome = MessageOutcome.POLICY_DENIED
            persisted_evidence = ()
        else:
            answer = outcome.reason
            persisted_outcome = MessageOutcome.TECHNICAL_FAILURE
            persisted_evidence = ()
        message_repository.add(
            with_question.append_message(
                role=MessageRole.ASSISTANT,
                content=answer,
                outcome=persisted_outcome,
                evidence=persisted_evidence,
            ),
            workspace_id=workspace_id,
        )
        return outcome
