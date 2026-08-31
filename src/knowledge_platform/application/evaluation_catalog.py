"""Application-facing evaluation suite discovery."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SuiteSummary:
    key: str
    name: str
    version: str
    case_count: int
    sha256: str


class SuiteCatalogPort(Protocol):
    def list_summaries(self) -> list[SuiteSummary]: ...


class EvaluationCatalogService:
    def __init__(self, catalog: SuiteCatalogPort) -> None:
        self._catalog = catalog

    def list_suites(self) -> list[SuiteSummary]:
        return self._catalog.list_summaries()
