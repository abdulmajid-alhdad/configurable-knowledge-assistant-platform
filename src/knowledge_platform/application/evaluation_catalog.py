"""Application-facing, version-controlled evaluation suite discovery."""
from dataclasses import dataclass
from typing import Protocol

from knowledge_platform.modules.evaluation.domain.contracts import (
    EvaluationSuite,
    EvaluationType,
)


@dataclass(frozen=True, slots=True)
class SuiteSummary:
    key: str
    name: str
    version: str
    case_count: int
    sha256: str
    evaluation_types: tuple[str, ...]
    supported: bool


@dataclass(frozen=True, slots=True)
class SuiteArtifact:
    """Safe application representation of one immutable suite artifact."""

    suite: EvaluationSuite
    sha256: str


class SuiteCatalogPort(Protocol):
    def list_summaries(self) -> list[SuiteSummary]: ...
    def get_artifact(self, suite_key: str) -> SuiteArtifact | None: ...


class EvaluationCatalogService:
    def __init__(self, catalog: SuiteCatalogPort) -> None:
        self._catalog = catalog

    def list_suites(self) -> list[SuiteSummary]:
        return self._catalog.list_summaries()

    def get_suite(self, suite_key: str) -> SuiteArtifact | None:
        return self._catalog.get_artifact(suite_key)


def suite_is_supported(suite: EvaluationSuite) -> bool:
    """MODEL_ASSISTED stays unavailable until a production judge exists."""

    return all(case.type is not EvaluationType.MODEL_ASSISTED for case in suite.cases)
