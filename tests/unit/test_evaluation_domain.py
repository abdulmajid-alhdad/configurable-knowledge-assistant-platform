"""Focused tests for evaluation domain contracts."""

from dataclasses import FrozenInstanceError

import pytest

from knowledge_platform.modules.evaluation.domain.contracts import (
    EvaluationCase,
    EvaluationRun,
    EvaluationRunLifecycle,
    EvaluationSuite,
    EvaluationType,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId


def case(key: str = "case-1") -> EvaluationCase:
    return EvaluationCase(
        key=key,
        type=EvaluationType.DETERMINISTIC,
        query=" query ",
        expected_source_ids=frozenset({KnowledgeSourceId.new()}),
    )


def suite(*cases_: EvaluationCase) -> EvaluationSuite:
    return EvaluationSuite(key="suite", version="1", name=" Suite ", cases=cases_ or (case(),))


def test_evaluation_type_values_are_exact() -> None:
    assert {item.value for item in EvaluationType} == {
        "deterministic", "reference_based", "model_assisted"
    }


def test_case_normalizes_and_is_immutable() -> None:
    value = EvaluationCase(
        key=" key ", type=EvaluationType.REFERENCE_BASED, query=" query ",
        expected_source_ids=frozenset(), reference_answer=" answer ",
    )
    assert (value.key, value.query, value.reference_answer) == ("key", "query", "answer")
    with pytest.raises(FrozenInstanceError):
        value.__setattr__("key", "changed")


@pytest.mark.parametrize("field", ["key", "query"])
def test_case_rejects_blank_required_text(field: str) -> None:
    kwargs = {
        "key": "key",
        "type": EvaluationType.DETERMINISTIC,
        "query": "query",
        "expected_source_ids": frozenset(),
    }
    kwargs[field] = " "
    with pytest.raises(ValueError):
        EvaluationCase(**kwargs)


def test_suite_requires_cases_and_unique_keys() -> None:
    with pytest.raises(ValueError):
        EvaluationSuite(key="s", version="1", name="n", cases=())
    with pytest.raises(ValueError, match="unique"):
        suite(case("same"), case("same"))
    valid = suite(case("a"), case("b"))
    assert valid.name == "Suite"
    with pytest.raises(FrozenInstanceError):
        valid.__setattr__("name", "changed")


def test_run_lifecycle_values_are_exact() -> None:
    assert {item.value for item in EvaluationRunLifecycle} == {
        "created", "running", "completed", "failed"
    }


def test_run_creation_start_and_record_are_immutable() -> None:
    run = EvaluationRun.create(suite=suite(case("a"), case("b")))
    assert run.lifecycle is EvaluationRunLifecycle.CREATED
    running = run.start()
    recorded = running.record(case_key="a")
    assert run.id == running.id == recorded.id
    assert recorded.results == frozenset({"a"})
    assert run.results == frozenset()


def test_run_record_requires_running_known_and_unique_case() -> None:
    run = EvaluationRun.create(suite=suite())
    with pytest.raises(ValueError):
        run.record(case_key="case-1")
    running = run.start()
    with pytest.raises(ValueError, match="not part"):
        running.record(case_key="unknown")
    recorded = running.record(case_key="case-1")
    with pytest.raises(ValueError, match="already"):
        recorded.record(case_key="case-1")


def test_run_completion_requires_exact_case_set() -> None:
    running = EvaluationRun.create(suite=suite(case("a"), case("b"))).start()
    with pytest.raises(ValueError, match="exactly"):
        running.record(case_key="a").complete()
    completed = running.record(case_key="a").record(case_key="b").complete()
    assert completed.lifecycle is EvaluationRunLifecycle.COMPLETED
    assert completed.results == frozenset({"a", "b"})


def test_run_failure_and_terminal_transitions() -> None:
    failed = EvaluationRun.create(suite=suite()).start().fail()
    assert failed.lifecycle is EvaluationRunLifecycle.FAILED
    with pytest.raises(ValueError):
        failed.start()
    with pytest.raises(ValueError):
        failed.record(case_key="case-1")
    with pytest.raises(ValueError):
        failed.complete()
    with pytest.raises(ValueError):
        failed.fail()
    completed = EvaluationRun.create(suite=suite()).start().record(case_key="case-1").complete()
    with pytest.raises(ValueError):
        completed.fail()
