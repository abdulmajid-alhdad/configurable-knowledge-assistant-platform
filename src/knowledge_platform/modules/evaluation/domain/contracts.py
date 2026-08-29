"""Framework-independent evaluation domain contracts."""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self

from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId

from ._validation import required_text
from .identifiers import EvaluationRunId


class EvaluationType(StrEnum):
    DETERMINISTIC = "deterministic"
    REFERENCE_BASED = "reference_based"
    MODEL_ASSISTED = "model_assisted"


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    key: str
    type: EvaluationType
    query: str
    expected_source_ids: frozenset[KnowledgeSourceId]
    reference_answer: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", required_text(self.key, field="key"))
        if not isinstance(self.type, EvaluationType):
            raise TypeError("type must be an EvaluationType")
        object.__setattr__(self, "query", required_text(self.query, field="query"))
        if not isinstance(self.expected_source_ids, frozenset):
            raise TypeError("expected_source_ids must be a frozenset")
        if not all(
            isinstance(source_id, KnowledgeSourceId)
            for source_id in self.expected_source_ids
        ):
            raise TypeError("expected_source_ids must contain KnowledgeSourceId values")
        if self.reference_answer is not None:
            object.__setattr__(
                self,
                "reference_answer",
                required_text(self.reference_answer, field="reference_answer"),
            )


@dataclass(frozen=True, slots=True)
class EvaluationSuite:
    key: str
    version: str
    name: str
    cases: tuple[EvaluationCase, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", required_text(self.key, field="key"))
        object.__setattr__(self, "version", required_text(self.version, field="version"))
        object.__setattr__(self, "name", required_text(self.name, field="name"))
        if not isinstance(self.cases, tuple):
            raise TypeError("cases must be a tuple")
        if not self.cases:
            raise ValueError("suite must contain at least one EvaluationCase")
        if not all(isinstance(case, EvaluationCase) for case in self.cases):
            raise TypeError("cases must contain only EvaluationCase values")
        keys = [case.key for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("case keys must be unique within a suite")


class EvaluationRunLifecycle(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    id: EvaluationRunId
    suite: EvaluationSuite
    lifecycle: EvaluationRunLifecycle
    results: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.id, EvaluationRunId):
            raise TypeError("id must be an EvaluationRunId")
        if not isinstance(self.suite, EvaluationSuite):
            raise TypeError("suite must be an EvaluationSuite")
        if not isinstance(self.lifecycle, EvaluationRunLifecycle):
            raise TypeError("lifecycle must be an EvaluationRunLifecycle")
        if not isinstance(self.results, frozenset):
            raise TypeError("results must be a frozenset")
        if not all(isinstance(key, str) for key in self.results):
            raise TypeError("results must contain case keys as strings")

    @classmethod
    def create(cls, *, suite: EvaluationSuite) -> Self:
        return cls(
            id=EvaluationRunId.new(),
            suite=suite,
            lifecycle=EvaluationRunLifecycle.CREATED,
            results=frozenset(),
        )

    def start(self) -> Self:
        return self._transition(
            expected=EvaluationRunLifecycle.CREATED,
            target=EvaluationRunLifecycle.RUNNING,
            operation="start",
        )

    def record(self, *, case_key: str) -> Self:
        if self.lifecycle is not EvaluationRunLifecycle.RUNNING:
            raise ValueError("record is valid only while RUNNING")
        normalized = required_text(case_key, field="case_key")
        suite_keys = {case.key for case in self.suite.cases}
        if normalized not in suite_keys:
            raise ValueError("case_key is not part of the evaluation suite")
        if normalized in self.results:
            raise ValueError("case result has already been recorded")
        return replace(self, results=self.results | {normalized})

    def complete(self) -> Self:
        if self.lifecycle is not EvaluationRunLifecycle.RUNNING:
            raise ValueError("complete is valid only while RUNNING")
        expected = frozenset(case.key for case in self.suite.cases)
        if self.results != expected:
            raise ValueError("completion requires exactly one result for every suite case")
        return replace(self, lifecycle=EvaluationRunLifecycle.COMPLETED)

    def fail(self) -> Self:
        return self._transition(
            expected=EvaluationRunLifecycle.RUNNING,
            target=EvaluationRunLifecycle.FAILED,
            operation="fail",
        )

    def _transition(
        self,
        *,
        expected: EvaluationRunLifecycle,
        target: EvaluationRunLifecycle,
        operation: str,
    ) -> Self:
        if self.lifecycle is not expected:
            raise ValueError(f"{operation} is invalid from {self.lifecycle.value}")
        return replace(self, lifecycle=target)
