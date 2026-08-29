"""Small complete Document RAG orchestration using provider-neutral ports."""

from typing import Any

from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.roles import MessageRole
from knowledge_platform.modules.document_knowledge.ports import (
    EmbeddingGatewayPort,
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


class DocumentRagService:
    def __init__(
        self,
        *,
        embeddings: EmbeddingGatewayPort,
        vectors: VectorSearchPort,
        model: ModelPort,
        egress: DataEgressPolicy,
    ) -> None:
        self.embeddings, self.vectors, self.model, self.egress = embeddings, vectors, model, egress

    def ask(
        self,
        *,
        workspace_id: WorkspaceId,
        assistant_id: AssistantId,
        question: str,
        source_ids: frozenset[KnowledgeSourceId],
        private_data: bool = True,
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
        try:
            query_vector = self.embeddings.embed_query(question)
            found: tuple[Any, ...] = self.vectors.search(
                workspace_id=workspace_id, source_ids=plan.source_ids, query=query_vector
            )
            result = RetrievalResult(
                plan=plan,
                items=tuple(
                    RetrievedContent(
                        source_id=c.source_id,
                        content=c.content,
                        provenance_locator=c.provenance_locator,
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
            )
            if not evidence:
                return grounding_outcome(answer="", evidence=())
            if (
                self.egress.decide(
                    processing_location=ProcessingLocation.EXTERNAL,
                    contains_private_data=private_data,
                )
                is PolicyDecision.DENY
            ):
                return PolicyDenied(reason="external private-data egress denied")
            answer = self.model.generate(
                question=question, context="\n".join(e.content for e in evidence)
            )
            return grounding_outcome(answer=answer, evidence=evidence)
        except Exception as exc:
            return TechnicalFailure(reason=str(exc) or "document RAG failed")

    def ask_in_conversation(
        self, *, conversation: Conversation, workspace_id: WorkspaceId,
        assistant_id: AssistantId, question: str, source_ids: frozenset[KnowledgeSourceId],
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
            source_ids=source_ids,
        )
        if isinstance(outcome, GroundedAnswer):
            answer = outcome.answer
        elif isinstance(outcome, InsufficientEvidence):
            answer = outcome.reason
        elif isinstance(outcome, PolicyDenied):
            answer = outcome.reason
        else:
            answer = outcome.reason
        message_repository.add(
            with_question.append_message(role=MessageRole.ASSISTANT, content=answer),
            workspace_id=workspace_id,
        )
        return outcome
