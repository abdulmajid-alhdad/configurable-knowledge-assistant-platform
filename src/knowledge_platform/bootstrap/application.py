"""Single production composition root for application services."""
# ruff: noqa: E501

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.assistant_conversations import AssistantConversationService
from knowledge_platform.application.assistant_knowledge_scope import AssistantKnowledgeScopeService
from knowledge_platform.application.assistants import AssistantService
from knowledge_platform.application.document_ingestion import DocumentIngestionService
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.application.evaluation_catalog import EvaluationCatalogService
from knowledge_platform.application.document_removal import DocumentRemovalService
from knowledge_platform.application.knowledge_ingestion import KnowledgeIngestionService
from knowledge_platform.application.knowledge_sources import KnowledgeSourceService
from knowledge_platform.application.workspaces import WorkspaceService
from knowledge_platform.config.database import PlatformDatabaseSettings
from knowledge_platform.config.runtime import RuntimeSettings
from knowledge_platform.infrastructure.credentials.environment import EnvironmentCredentialResolver
from knowledge_platform.infrastructure.documents.artifacts import FilesystemOriginalArtifactStore
from knowledge_platform.infrastructure.documents.parsers import parser_for_suffix
from knowledge_platform.infrastructure.evaluation.catalog import FilesystemSuiteCatalog
from knowledge_platform.infrastructure.embeddings.remote import RemoteEmbeddingAdapter
from knowledge_platform.infrastructure.models.remote import RemoteModelAdapter
from knowledge_platform.infrastructure.persistence.database import (
    create_platform_engine,
    create_session_factory,
)
from knowledge_platform.infrastructure.persistence.repositories import (
    AssistantKnowledgeSourceRepository,
    AssistantRepository,
    ConversationRepository,
    KnowledgeSourceRepository,
    MessageRepository,
    WorkspaceRepository,
)
from knowledge_platform.infrastructure.persistence.workspace_context import workspace_session_scope
from knowledge_platform.infrastructure.vector_search.postgres import (
    DocumentRepresentationRepository,
    PgvectorDocumentSearchAdapter,
)
from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.document_knowledge.artifacts import OriginalArtifact
from knowledge_platform.modules.document_knowledge.ports import VectorSearchPort
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    workspace: WorkspaceRepository
    assistant: AssistantRepository
    knowledge_source: KnowledgeSourceRepository
    representation: DocumentRepresentationRepository
    conversation: ConversationRepository
    message: MessageRepository
    assistant_sources: AssistantKnowledgeSourceRepository


@dataclass(frozen=True, slots=True)
class ApplicationRuntime:
    settings: RuntimeSettings
    engine: Engine
    session_factory: sessionmaker[Session]
    credentials: EnvironmentCredentialResolver
    egress: DataEgressPolicy

    def repositories(self, session: Session) -> RepositoryBundle:
        return RepositoryBundle(
            workspace=WorkspaceRepository(session),
            assistant=AssistantRepository(session),
            knowledge_source=KnowledgeSourceRepository(session),
            representation=DocumentRepresentationRepository(session),
            conversation=ConversationRepository(session),
            message=MessageRepository(session),
            assistant_sources=AssistantKnowledgeSourceRepository(session),
        )

    def management_services(self) -> Any:
        runtime = self

        class Services:
            def create_workspace(self, name: str) -> Any:
                value = Workspace.create(name=name)
                with workspace_session_scope(runtime.session_factory, value.id) as session:
                    runtime.repositories(session).workspace.add(value)
                return value

            def get_workspace(self, workspace_id: UUID) -> Any:
                with workspace_session_scope(runtime.session_factory, WorkspaceId(workspace_id)) as session:
                    return WorkspaceService(runtime.repositories(session).workspace).get(WorkspaceId(workspace_id))

            def create_assistant(self, workspace_id: UUID, payload: Any) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    if WorkspaceService(runtime.repositories(session).workspace).get(wid) is None:
                        raise LookupError("workspace not found")
                    return AssistantService(runtime.repositories(session).assistant).create(
                        workspace_id=wid, name=payload.name, description=payload.description,
                        instructions=payload.instructions, language=payload.language,
                        provider=payload.provider, model_reference=payload.model_reference,
                    )

            def list_assistants(self, workspace_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return AssistantService(runtime.repositories(session).assistant).list(wid)

            def get_assistant(self, workspace_id: UUID, assistant_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return AssistantService(runtime.repositories(session).assistant).get(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id)
                    )

            def update_assistant(self, workspace_id: UUID, assistant_id: UUID, payload: Any) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return AssistantService(runtime.repositories(session).assistant).reconfigure(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id),
                        name=payload.name, description=payload.description,
                        instructions=payload.instructions, language=payload.language,
                        provider=payload.provider, model_reference=payload.model_reference,
                    )

            def create_source(self, workspace_id: UUID, payload: Any) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    if WorkspaceService(runtime.repositories(session).workspace).get(wid) is None:
                        raise LookupError("workspace not found")
                    return KnowledgeSourceService(runtime.repositories(session).knowledge_source).register(
                        workspace_id=wid, name=payload.name, kind=KnowledgeSourceKind(payload.kind)
                    )

            def list_sources(self, workspace_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return KnowledgeSourceService(runtime.repositories(session).knowledge_source).list(wid)

            def get_source(self, workspace_id: UUID, source_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return KnowledgeSourceService(runtime.repositories(session).knowledge_source).get(
                        workspace_id=wid, source_id=KnowledgeSourceId(source_id)
                    )

            async def upload_source(self, workspace_id: UUID, source_id: UUID,
                                    chunks: AsyncIterator[bytes], filename: str,
                                    media_type: str | None) -> OriginalArtifact:
                data: list[bytes] = []
                total = 0
                async for chunk in chunks:
                    total += len(chunk)
                    if total > runtime.settings.max_artifact_bytes:
                        raise ValueError("artifact exceeds maximum size")
                    data.append(chunk)
                wid = WorkspaceId(workspace_id)
                sid = KnowledgeSourceId(source_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    source = runtime.repositories(session).knowledge_source.get(
                        source_id=sid, workspace_id=wid
                    )
                    if source is None:
                        raise LookupError("source not found")
                return runtime.artifact_store().store(
                    workspace_id=wid, source_id=sid, chunks=data,
                    filename=filename, media_type=media_type,
                    max_bytes=runtime.settings.max_artifact_bytes,
                )

            def process_source(self, workspace_id: UUID, source_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                sid = KnowledgeSourceId(source_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    repos = runtime.repositories(session)
                    source = repos.knowledge_source.get(source_id=sid, workspace_id=wid)
                    if source is None:
                        raise LookupError("source not found")
                    return runtime.knowledge_ingestion_service().process(
                        workspace_id=wid, source=source,
                        source_repository=repos.knowledge_source,
                        representation_repository=repos.representation,
                        embedding_profile=runtime.settings.embedding_model or "configured",
                    )

            def attach_source(self, workspace_id: UUID, assistant_id: UUID, source_id: UUID) -> None:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    repos = runtime.repositories(session)
                    AssistantKnowledgeScopeService(
                        assistants=repos.assistant, sources=repos.knowledge_source,
                        associations=repos.assistant_sources,
                    ).attach(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id),
                        source_id=KnowledgeSourceId(source_id),
                    )

            def detach_source(self, workspace_id: UUID, assistant_id: UUID, source_id: UUID) -> None:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    runtime.assistant_scope_service(session).detach(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id),
                        source_id=KnowledgeSourceId(source_id),
                    )

            def list_attached_sources(self, workspace_id: UUID, assistant_id: UUID) -> list[Any]:
                wid = WorkspaceId(workspace_id)
                aid = AssistantId(assistant_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    repos = runtime.repositories(session)
                    assistant = repos.assistant.get(assistant_id=aid, workspace_id=wid)
                    if assistant is None:
                        raise LookupError("assistant not found")
                    ids = repos.assistant_sources.list_source_ids(
                        assistant_id=aid, workspace_id=wid
                    )
                    return [
                        source for source in repos.knowledge_source.list_for_workspace(wid)
                        if source.id in ids
                    ]

            def create_conversation(self, workspace_id: UUID, assistant_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).create(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id)
                    )

            def get_conversation(self, workspace_id: UUID, conversation_id: UUID) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).get(
                        workspace_id=wid,
                        conversation_id=ConversationId(conversation_id),
                    )

            def ask_conversation(self, workspace_id: UUID, conversation_id: UUID, question: str) -> Any:
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).ask(
                        workspace_id=wid,
                        conversation_id=ConversationId(conversation_id),
                        question=question,
                    )

        return Services()

    def assistant_scope_service(self, session: Session) -> AssistantKnowledgeScopeService:
        repos = self.repositories(session)
        return AssistantKnowledgeScopeService(
            assistants=repos.assistant,
            sources=repos.knowledge_source,
            associations=repos.assistant_sources,
        )

    def conversation_service(self, session: Session) -> AssistantConversationService:
        repos = self.repositories(session)
        return AssistantConversationService(
            assistants=repos.assistant, sources=repos.knowledge_source,
            associations=repos.assistant_sources, conversations=repos.conversation,
            messages=repos.message, rag=self.rag_service(session),
        )

    def embedding_gateway(self) -> RemoteEmbeddingAdapter:
        if self.settings.embedding_endpoint is None or self.settings.embedding_model is None:
            raise RuntimeError("embedding provider configuration is incomplete")
        if self.settings.embedding_dimensions is None:
            raise RuntimeError("embedding dimensions are not configured")
        return RemoteEmbeddingAdapter(
            endpoint=self.settings.embedding_endpoint,
            model_reference=self.settings.embedding_model,
            api_key=self.credentials.resolve(self.settings.credential_for_embedding),
            dimensions=self.settings.embedding_dimensions,
        )

    def model_gateway(self) -> RemoteModelAdapter:
        if self.settings.model_endpoint is None or self.settings.model_reference is None:
            raise RuntimeError("model provider configuration is incomplete")
        return RemoteModelAdapter(
            endpoint=self.settings.model_endpoint,
            model_reference=self.settings.model_reference,
            api_key=self.credentials.resolve(self.settings.credential_for_model),
        )

    def ingestion_service(self) -> DocumentIngestionService:
        return DocumentIngestionService(embeddings=self.embedding_gateway())

    def artifact_store(self) -> FilesystemOriginalArtifactStore:
        return FilesystemOriginalArtifactStore(self.settings.artifact_root)

    def knowledge_ingestion_service(self) -> KnowledgeIngestionService:
        return KnowledgeIngestionService(
            artifacts=self.artifact_store(), ingestion=self.ingestion_service(),
            max_artifact_bytes=self.settings.max_artifact_bytes,
            parser_factory=parser_for_suffix,
        )

    def removal_service(self) -> DocumentRemovalService:
        return DocumentRemovalService()

    def evaluation_catalog(self) -> EvaluationCatalogService:
        return EvaluationCatalogService(FilesystemSuiteCatalog(Path("evaluation/suites")))

    def rag_service(self, session: Session) -> DocumentRagService:
        return DocumentRagService(
            embeddings=self.embedding_gateway(),
            vectors=cast(VectorSearchPort, PgvectorDocumentSearchAdapter(session)),
            model=self.model_gateway(),
            egress=self.egress,
        )


def create_runtime(settings: RuntimeSettings | None = None) -> ApplicationRuntime:
    runtime_settings = settings or RuntimeSettings()
    if runtime_settings.database_dsn is None:
        raise RuntimeError("platform database configuration is incomplete")
    database_settings = PlatformDatabaseSettings(
        platform_database_dsn=cast(
            SecretStr, runtime_settings.database_dsn.get_secret_value()
        )
    )
    engine = create_platform_engine(database_settings)
    return ApplicationRuntime(
        settings=runtime_settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        credentials=EnvironmentCredentialResolver(),
        egress=DataEgressPolicy(runtime_settings.external_private_data_allowed),
    )
