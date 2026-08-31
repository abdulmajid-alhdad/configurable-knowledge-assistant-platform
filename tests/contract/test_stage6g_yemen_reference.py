"""Configurability contracts for the Yemen reference package."""
from knowledge_platform.reference.yemen_history import DEFINITION, artifact_path, build_reference
from knowledge_platform.reference.yemen_history import YemenHistoryReferenceProvisioner
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import ModelConfiguration, RetrievalConfiguration


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


def test_reference_provisioner_uses_generic_boundaries() -> None:
    calls: list[str] = []
    workspace = Workspace.create(name=DEFINITION.workspace_name)
    assistant = Assistant.create(
        workspace_id=workspace.id, name=DEFINITION.assistant_name,
        description="reference", instructions=DEFINITION.assistant_instructions,
        language="ar", model_configuration=ModelConfiguration(provider="remote", model_reference="configured"),
        retrieval_configuration=RetrievalConfiguration(),
    )
    source = KnowledgeSource.create(
        workspace_id=workspace.id, name=DEFINITION.source_name, kind=KnowledgeSourceKind.DOCUMENT
    )

    class Workspaces:
        def create(self, *, name: str) -> Workspace:
            calls.append("workspace")
            return workspace

    class Assistants:
        def create(self, **kwargs: object) -> Assistant:
            calls.append("assistant")
            return assistant

    class Sources:
        def register(self, **kwargs: object) -> KnowledgeSource:
            calls.append("source")
            return source

    class Artifacts:
        def store(self, **kwargs: object) -> object:
            calls.append("artifact")
            return object()

    class Ingestion:
        def process(self, **kwargs: object) -> KnowledgeSource:
            calls.append("ingestion")
            return source

    class Scope:
        def attach(self, **kwargs: object) -> None:
            calls.append("scope")

    provisioner = YemenHistoryReferenceProvisioner(
        workspaces=Workspaces(), assistants=Assistants(), sources=Sources(),
        artifacts=Artifacts(), ingestion=Ingestion(), scope=Scope(),
        assistant_repository=object(), source_repository=object(),
        representation_repository=object(),
    )
    provisioner.provision()
    assert calls == ["workspace", "assistant", "source", "artifact", "ingestion", "scope"]
