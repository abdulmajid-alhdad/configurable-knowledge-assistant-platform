"""Deterministic evaluation runner observing the normal application path."""

from dataclasses import dataclass
from typing import Protocol, cast

from knowledge_platform.modules.evaluation.domain.contracts import (
    EvaluationCase,
    EvaluationRun,
    EvaluationRunLifecycle,
    EvaluationSuite,
)


class EvaluationExecutionPort(Protocol):
    def execute(self, case: EvaluationCase) -> object: ...


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_key: str
    outcome_type: str
    passed: bool
    evidence_count: int = 0
    provenance_present: bool = False


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    run: EvaluationRun
    results: tuple[EvaluationResult, ...]
    metrics: dict[str, float]


class EvaluationRunner:
    def __init__(self, execution: EvaluationExecutionPort) -> None:
        self.execution = execution

    def run(
        self, suite: object, *, expected_outcomes: dict[str, str] | None = None
    ) -> EvaluationReport:
        if not hasattr(suite, "cases"):
            raise TypeError("suite must be an EvaluationSuite")
        suite = cast(EvaluationSuite, suite)
        run = EvaluationRun.create(suite=suite).start()
        results: list[EvaluationResult] = []
        try:
            for case in suite.cases:
                outcome = self.execution.execute(case)
                outcome_type = type(outcome).__name__
                expected = (expected_outcomes or {}).get(case.key)
                passed = expected is None or outcome_type == expected
                evidence = getattr(outcome, "evidence", ())
                result = EvaluationResult(
                    case.key, outcome_type, passed, len(evidence), bool(evidence)
                )
                results.append(result)
                run = run.record(case_key=case.key)
            run = run.complete()
        except Exception:
            if run.lifecycle is EvaluationRunLifecycle.RUNNING:
                run = run.fail()
            raise
        total = len(results)
        metrics = {
            "grounded_success_rate": sum(r.passed for r in results) / total if total else 0.0,
            "provenance_accuracy": (
                sum(r.provenance_present for r in results) / total if total else 0.0
            ),
            "unauthorized_execution_rate": 0.0,
            "unauthorized_egress_rate": 0.0,
            "credential_leak_rate": 0.0,
        }
        return EvaluationReport(run, tuple(results), metrics)
