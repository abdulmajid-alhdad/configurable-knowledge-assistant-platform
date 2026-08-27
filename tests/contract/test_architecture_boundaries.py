"""Static checks for the accepted Ports and Adapters dependency direction."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "knowledge_platform"

FORBIDDEN_PROJECT_ROOTS = (
    "knowledge_platform.infrastructure",
    "knowledge_platform.delivery",
)

DOMAIN_FORBIDDEN_EXTERNALS = (
    "fastapi",
    "sqlalchemy",
    "psycopg",
    "pgvector",
    "pypdf",
    "docx",
    "sentence_transformers",
)

APPLICATION_FORBIDDEN_EXTERNALS = (
    "fastapi",
    "sqlalchemy",
    "psycopg",
)


@dataclass(frozen=True)
class BoundaryViolation:
    """A forbidden dependency found in a core architectural layer."""

    file: Path
    imported_module: str
    layer: str
    boundary: str

    def describe(self) -> str:
        return (
            f"{self.file}: {self.layer} imports {self.imported_module!r}; "
            f"violated boundary: {self.boundary}"
        )


def _source_layer(path: Path, source_root: Path) -> str | None:
    parts = path.relative_to(source_root).parts
    for layer in ("domain", "application", "ports"):
        if layer in parts:
            return layer.upper()
    return None


def _package_name(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root)
    parent_parts = relative.parent.parts
    return ".".join(("knowledge_platform", *parent_parts))


def _resolve_relative_import(module: str | None, level: int, package: str) -> str | None:
    package_parts = package.split(".")
    parents_to_remove = level - 1
    if parents_to_remove >= len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - parents_to_remove]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _imported_modules(source: str, package: str) -> list[str]:
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                resolved = _resolve_relative_import(node.module, node.level, package)
                if resolved is not None:
                    imports.append(resolved)
            elif node.module is not None:
                imports.append(node.module)
    return imports


def _matches_root(imported_module: str, forbidden_root: str) -> bool:
    return imported_module == forbidden_root or imported_module.startswith(f"{forbidden_root}.")


def _violations_for_source(
    source: str,
    *,
    file: Path,
    layer: str,
    package: str,
) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    external_roots: tuple[str, ...] = ()
    if layer == "DOMAIN":
        external_roots = DOMAIN_FORBIDDEN_EXTERNALS
    elif layer == "APPLICATION":
        external_roots = APPLICATION_FORBIDDEN_EXTERNALS

    for imported_module in _imported_modules(source, package):
        for forbidden_root in FORBIDDEN_PROJECT_ROOTS:
            if _matches_root(imported_module, forbidden_root):
                violations.append(
                    BoundaryViolation(
                        file=file,
                        imported_module=imported_module,
                        layer=layer,
                        boundary=f"{layer} must not depend on {forbidden_root}",
                    )
                )
        for forbidden_root in external_roots:
            if _matches_root(imported_module, forbidden_root):
                violations.append(
                    BoundaryViolation(
                        file=file,
                        imported_module=imported_module,
                        layer=layer,
                        boundary=(
                            f"{layer} must not depend on implementation library {forbidden_root}"
                        ),
                    )
                )
    return violations


def _repository_violations(source_root: Path = SOURCE_ROOT) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for path in sorted(source_root.rglob("*.py")):
        layer = _source_layer(path, source_root)
        if layer is None:
            continue
        violations.extend(
            _violations_for_source(
                path.read_text(encoding="utf-8"),
                file=path,
                layer=layer,
                package=_package_name(path, source_root),
            )
        )
    return violations


def test_repository_respects_architecture_boundaries() -> None:
    violations = _repository_violations()
    assert not violations, "Architecture boundary violations:\n" + "\n".join(
        violation.describe() for violation in violations
    )


def test_standard_library_and_inward_imports_are_allowed() -> None:
    source = """
import typing
from pathlib import Path
from knowledge_platform.modules.conversation.domain import model
"""
    violations = _violations_for_source(
        source,
        file=Path("example_application.py"),
        layer="APPLICATION",
        package="knowledge_platform.modules.conversation.application",
    )
    assert violations == []


def test_domain_infrastructure_import_is_forbidden() -> None:
    violations = _violations_for_source(
        "import knowledge_platform.infrastructure.persistence",
        file=Path("example_domain.py"),
        layer="DOMAIN",
        package="knowledge_platform.modules.conversation.domain",
    )
    assert [violation.imported_module for violation in violations] == [
        "knowledge_platform.infrastructure.persistence"
    ]


def test_domain_implementation_library_import_is_forbidden() -> None:
    violations = _violations_for_source(
        "from sqlalchemy import select",
        file=Path("example_domain.py"),
        layer="DOMAIN",
        package="knowledge_platform.modules.conversation.domain",
    )
    assert [violation.imported_module for violation in violations] == ["sqlalchemy"]


def test_application_delivery_import_is_forbidden() -> None:
    violations = _violations_for_source(
        "from knowledge_platform.delivery.api import router",
        file=Path("example_application.py"),
        layer="APPLICATION",
        package="knowledge_platform.modules.conversation.application",
    )
    assert [violation.imported_module for violation in violations] == [
        "knowledge_platform.delivery.api"
    ]


def test_structurally_clear_relative_import_is_resolved() -> None:
    violations = _violations_for_source(
        "from ....infrastructure import persistence",
        file=Path("example_domain.py"),
        layer="DOMAIN",
        package="knowledge_platform.modules.conversation.domain",
    )
    assert [violation.imported_module for violation in violations] == [
        "knowledge_platform.infrastructure"
    ]
