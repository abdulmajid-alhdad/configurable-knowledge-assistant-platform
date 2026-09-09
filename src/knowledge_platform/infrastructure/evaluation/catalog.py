"""Filesystem-backed evaluation suite catalog."""
from pathlib import Path

from knowledge_platform.application.evaluation_catalog import (
    SuiteArtifact,
    SuiteSummary,
    suite_is_supported,
)

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
                evaluation_types=tuple(
                    sorted({case.type.value for case in artifact.suite.cases})
                ),
                supported=suite_is_supported(artifact.suite),
            ))
        return result

    def get_artifact(self, suite_key: str) -> SuiteArtifact | None:
        if not isinstance(suite_key, str) or not suite_key.strip():
            return None
        normalized = suite_key.strip()
        for path in sorted(self._root.glob("*.json")):
            artifact = load_suite(path)
            if artifact.suite.key == normalized:
                return SuiteArtifact(suite=artifact.suite, sha256=artifact.sha256)
        return None
