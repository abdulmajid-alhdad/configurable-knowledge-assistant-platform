"""Configurability contracts for the Yemen reference package."""
from knowledge_platform.reference.yemen_history import DEFINITION, artifact_path, build_reference


def test_reference_is_declarative_and_has_supported_artifact() -> None:
    assert DEFINITION.key == "yemen_history"
    assert DEFINITION.artifact_name.endswith(".md")
    assert artifact_path().is_file()
    assert "DATABASE" not in artifact_path().read_text(encoding="utf-8")


def test_reference_uses_ordinary_generic_domain_objects() -> None:
    workspace, assistant, source, scope = build_reference()
    assert workspace.name == DEFINITION.workspace_name or workspace.name == "Yemen History Demo"
    assert assistant.name == DEFINITION.assistant_name
    assert source.workspace_id == workspace.id
    assert scope.allows(source)
