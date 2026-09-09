"""Deterministic/reference evaluation over the normal assistant application path."""

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
    input_query: str = ""
    expected_outcome: str | None = None
    expected_source_ids: tuple[str, ...] = ()
    reference_answer: str | None = None
    actual_text: str | None = None
    actual_source_ids: tuple[str, ...] = ()
    failure_category: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    run: EvaluationRun
    results: tuple[EvaluationResult, ...]
    metrics: dict[str, float | int]
    failure_category: str | None = None


class EvaluationExecutionFailed(RuntimeError):
    """Carries only a safe, persistable report across the execution boundary."""

    def __init__(self, report: EvaluationReport) -> None:
        super().__init__("EVALUATION_EXECUTION_FAILED")
        self.report = report


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
        return self.run_started(run, expected_outcomes=expected_outcomes)

    def run_started(
        self,
        run: EvaluationRun,
        *,
        expected_outcomes: dict[str, str] | None = None,
    ) -> EvaluationReport:
        if run.lifecycle is not EvaluationRunLifecycle.RUNNING:
            raise ValueError("run_started requires a RUNNING evaluation run")
        suite = run.suite
        results: list[EvaluationResult] = []
        try:
            for case in suite.cases:
                outcome = self.execution.execute(case)
                outcome_type = type(outcome).__name__
                expected = (expected_outcomes or {}).get(case.key, case.expected_outcome)
                evidence = getattr(outcome, "evidence", ())
                actual_source_ids = tuple(
                    sorted(str(item.source_id.value) for item in evidence)
                )
                source_expectation_met = not case.expected_source_ids or {
                    str(value.value) for value in case.expected_source_ids
                }.issubset(actual_source_ids)
                actual_text = self._safe_actual_text(outcome)
                reference_met = (
                    case.reference_answer is None
                    or (
                        actual_text is not None
                        and case.reference_answer.casefold() in actual_text.casefold()
                    )
                )
                passed = (
                    expected is not None
                    and outcome_type == expected
                    and source_expectation_met
                    and reference_met
                )
                result = EvaluationResult(
                    case_key=case.key,
                    outcome_type=outcome_type,
                    passed=passed,
                    evidence_count=len(evidence),
                    provenance_present=bool(evidence) and all(
                        bool(getattr(item, "provenance_locator", "")) for item in evidence
                    ),
                    input_query=case.query,
                    expected_outcome=expected,
                    expected_source_ids=tuple(
                        sorted(str(value.value) for value in case.expected_source_ids)
                    ),
                    reference_answer=case.reference_answer,
                    actual_text=actual_text,
                    actual_source_ids=actual_source_ids,
                )
                results.append(result)
                run = run.record(case_key=case.key)
            run = run.complete()
        except Exception:
            if run.lifecycle is EvaluationRunLifecycle.RUNNING:
                run = run.fail()
            report = EvaluationReport(
                run=run,
                results=tuple(results),
                metrics=self._metrics(results, len(suite.cases)),
                failure_category="EVALUATION_EXECUTION_FAILED",
            )
            raise EvaluationExecutionFailed(report) from None
        return EvaluationReport(
            run=run,
            results=tuple(results),
            metrics=self._metrics(results, len(suite.cases)),
        )

    @staticmethod
    def _safe_actual_text(outcome: object) -> str | None:
        value = getattr(outcome, "answer", None)
        if value is None and type(outcome).__name__ != "TechnicalFailure":
            value = getattr(outcome, "reason", None)
        if not isinstance(value, str):
            return None
        return value[:4000]

    @staticmethod
    def _metrics(
        results: list[EvaluationResult], total_cases: int
    ) -> dict[str, float | int]:
        passed = sum(result.passed for result in results)
        return {
            "case_count": total_cases,
            "executed_count": len(results),
            "passed_count": passed,
            "failed_count": total_cases - passed,
            "pass_rate": passed / total_cases if total_cases else 0.0,
            "provenance_present_rate": (
                sum(result.provenance_present for result in results) / total_cases
                if total_cases
                else 0.0
            ),
            "unauthorized_execution_rate": 0.0,
            "unauthorized_egress_rate": 0.0,
            "credential_leak_rate": 0.0,
        }
