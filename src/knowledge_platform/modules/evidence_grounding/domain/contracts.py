"""Immutable evidence, grounding decisions, and terminal outcomes."""

from dataclasses import dataclass
from enum import Enum

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId


def _required_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized


class GroundingDecision(Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class Evidence:
    """Content support with an opaque, domain-neutral provenance locator."""

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
class GroundedAnswer:
    answer: str
    evidence: tuple[Evidence, ...]
    decision: GroundingDecision = GroundingDecision.SUFFICIENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "answer", _required_text(self.answer, field="answer"))
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be a tuple")
        if not self.evidence:
            raise ValueError("grounded answer requires at least one Evidence")
        if not all(isinstance(item, Evidence) for item in self.evidence):
            raise TypeError("evidence must contain only Evidence values")
        if self.decision is not GroundingDecision.SUFFICIENT:
            raise ValueError("grounded answer decision must be SUFFICIENT")


@dataclass(frozen=True, slots=True)
class InsufficientEvidence:
    reason: str
    decision: GroundingDecision = GroundingDecision.INSUFFICIENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _required_text(self.reason, field="reason"))
        if self.decision is not GroundingDecision.INSUFFICIENT:
            raise ValueError("insufficient evidence decision must be INSUFFICIENT")


@dataclass(frozen=True, slots=True)
class PolicyDenied:
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _required_text(self.reason, field="reason"))


@dataclass(frozen=True, slots=True)
class TechnicalFailure:
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _required_text(self.reason, field="reason"))


type GroundingOutcome = (
    GroundedAnswer | InsufficientEvidence | PolicyDenied | TechnicalFailure
)


def grounding_outcome(*, answer: str, evidence: tuple[Evidence, ...]) -> GroundingOutcome:
    """Return insufficiency for zero evidence; otherwise construct a grounded answer."""
    if not isinstance(evidence, tuple):
        raise TypeError("evidence must be a tuple")
    if not evidence:
        return InsufficientEvidence(reason="no evidence supports an answer")
    return GroundedAnswer(answer=answer, evidence=evidence)
