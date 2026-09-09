"""Configurability contracts for the Yemen reference package."""
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.infrastructure.vector_search.store import VectorChunk, VectorSearchStore
from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    GroundedAnswer,
    InsufficientEvidence,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace
from knowledge_platform.reference.yemen_history import (
    DEFINITION,
    YemenHistoryReferenceProvisioner,
    artifact_path,
    build_reference,
)


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
        language="ar",
        model_configuration=ModelConfiguration(
            provider="remote", model_reference="configured"
        ),
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

    class Processing:
        def process(
            self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId,
            embedding_profile: str,
        ) -> KnowledgeSource:
            assert workspace_id == workspace.id
            assert source_id == source.id
            assert embedding_profile == "reference"
            calls.append("processing")
            return source

    class Scope:
        def attach(self, **kwargs: object) -> None:
            calls.append("scope")

    provisioner = YemenHistoryReferenceProvisioner(
        workspaces=Workspaces(), assistants=Assistants(), sources=Sources(),
        artifacts=Artifacts(), processing=Processing(), scope=Scope(),
    )
    provisioner.provision()
    assert calls == ["workspace", "assistant", "source", "artifact", "processing", "scope"]


def test_yemen_reference_supported_question_returns_grounded_answer() -> None:
    workspace, assistant, source, scope = build_reference()
    store = VectorSearchStore()
    content = artifact_path().read_text(encoding="utf-8").splitlines()[2]
    store.add(
        VectorChunk(
            workspace.id, source.id, content, "yemen_history.md#1",
            EmbeddingVector((1.0, 0.0)),
        )
    )

    class Embeddings:
        def embed_query(self, text: str) -> EmbeddingVector:
            return EmbeddingVector((1.0, 0.0))
        def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
            return tuple(EmbeddingVector((1.0, 0.0)) for _ in texts)

    class Model:
        def generate(self, *, question: str, context: str) -> str:
            assert content in context
            return "grounded"

    outcome = DocumentRagService(
        embeddings=Embeddings(), vectors=store, model=Model(), egress=DataEgressPolicy(True)
    ).ask(workspace_id=workspace.id, assistant_id=assistant.id,
          question="ما تاريخ صنعاء؟", source_ids=frozenset({source.id}))
    assert isinstance(outcome, GroundedAnswer)
    assert outcome.evidence[0].source_id == source.id
    assert outcome.evidence[0].provenance_locator == "yemen_history.md#1"


def test_yemen_reference_unsupported_and_detached_questions_are_insufficient() -> None:
    workspace, assistant, source, _ = build_reference()
    store = VectorSearchStore()

    class Embeddings:
        def embed_query(self, text: str) -> EmbeddingVector:
            return EmbeddingVector((1.0, 0.0))
        def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
            return ()

    class Model:
        def generate(self, *, question: str, context: str) -> str:
            raise AssertionError("model must not run without evidence")

    rag = DocumentRagService(
        embeddings=Embeddings(), vectors=store, model=Model(), egress=DataEgressPolicy(True)
    )
    unsupported = rag.ask(
        workspace_id=workspace.id, assistant_id=assistant.id,
        question="unsupported", source_ids=frozenset({source.id})
    )
    assert isinstance(unsupported, InsufficientEvidence)
    assert isinstance(rag.ask(workspace_id=workspace.id, assistant_id=assistant.id,
                              question="صنعاء", source_ids=frozenset()), InsufficientEvidence)
