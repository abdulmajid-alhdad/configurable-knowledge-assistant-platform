"""Strict, deterministic evaluation suite artifact loading."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from knowledge_platform.modules.evaluation.domain.contracts import (
    EvaluationCase,
    EvaluationSuite,
    EvaluationType,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId


@dataclass(frozen=True, slots=True)
class EvaluationSuiteArtifact:
    suite: EvaluationSuite
    reference: str
    sha256: str


def load_suite(path: Path) -> EvaluationSuiteArtifact:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"key", "version", "name", "cases"}:
        raise ValueError("suite must contain exactly key, version, name, and cases")
    if not isinstance(payload["cases"], list):
        raise ValueError("cases must be a list")
    cases = []
    for item in payload["cases"]:
        allowed = {"key", "type", "query", "expected_source_ids", "reference_answer"}
        if not isinstance(item, dict) or not set(item) <= allowed:
            raise ValueError("unknown suite case field")
        try:
            cases.append(
                EvaluationCase(
                    key=item["key"],
                    type=EvaluationType(item["type"]),
                    query=item["query"],
                    expected_source_ids=frozenset(
                        KnowledgeSourceId(UUID(value))
                        for value in item.get("expected_source_ids", [])
                    ),
                    reference_answer=item.get("reference_answer"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid evaluation case") from exc
    suite = EvaluationSuite(
        key=payload["key"], version=payload["version"], name=payload["name"], cases=tuple(cases)
    )
    return EvaluationSuiteArtifact(
        suite=suite, reference=str(path), sha256=hashlib.sha256(raw).hexdigest()
    )
