"""Filesystem-backed evaluation suite catalog."""
from pathlib import Path

from knowledge_platform.application.evaluation_catalog import SuiteSummary

from .suites import load_suite


class FilesystemSuiteCatalog:
    def __init__(self, root: Path) -> None:
        self._root = root

    def list_summaries(self) -> list[SuiteSummary]:
        result = []
        for path in sorted(self._root.glob("*.json")):
            artifact = load_suite(path)
            result.append(SuiteSummary(
                key=artifact.suite.key, name=artifact.suite.name,
                version=artifact.suite.version, case_count=len(artifact.suite.cases),
                sha256=artifact.sha256,
            ))
        return result
