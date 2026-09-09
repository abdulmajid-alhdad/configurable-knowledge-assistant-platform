"""Immutable conversation messages."""

from dataclasses import dataclass
from enum import StrEnum

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId

from .roles import MessageRole


class MessageOutcome(StrEnum):
    GROUNDED = "grounded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    POLICY_DENIED = "policy_denied"
    TECHNICAL_FAILURE = "technical_failure"


@dataclass(frozen=True, slots=True)
class MessageEvidence:
    source_id: KnowledgeSourceId
    content: str
    provenance_locator: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, KnowledgeSourceId):
            raise TypeError("source_id must be a KnowledgeSourceId")
        for field in ("content", "provenance_locator"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field} must not be blank")
            object.__setattr__(self, field, normalized)


@dataclass(frozen=True, slots=True)
class Message:
    sequence: int
    role: MessageRole
    content: str
    outcome: MessageOutcome | None = None
    evidence: tuple[MessageEvidence, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise TypeError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be a MessageRole")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        normalized = self.content.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        object.__setattr__(self, "content", normalized)
        if self.outcome is not None and not isinstance(self.outcome, MessageOutcome):
            raise TypeError("outcome must be a MessageOutcome when provided")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, MessageEvidence) for item in self.evidence
        ):
            raise TypeError("evidence must contain only MessageEvidence values")
        if self.role is MessageRole.USER and (self.outcome is not None or self.evidence):
            raise ValueError("user messages cannot carry assistant outcomes")
        if self.outcome is MessageOutcome.GROUNDED and not self.evidence:
            raise ValueError("grounded messages require evidence")
        if self.outcome is not MessageOutcome.GROUNDED and self.evidence:
            raise ValueError("only grounded messages may carry evidence")
