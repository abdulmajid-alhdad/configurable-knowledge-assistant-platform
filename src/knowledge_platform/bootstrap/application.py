"""Single production composition root for application services."""
# ruff: noqa: E501

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import AccessDenied
from knowledge_platform.application.assistant_conversations import AssistantConversationService
from knowledge_platform.application.assistant_knowledge_scope import AssistantKnowledgeScopeService
from knowledge_platform.application.assistants import AssistantService
from knowledge_platform.application.commercial import CommercialError
from knowledge_platform.application.document_ingestion import DocumentIngestionService
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.application.document_removal import DocumentRemovalService
from knowledge_platform.application.evaluation_catalog import EvaluationCatalogService
from knowledge_platform.application.evaluation_control import EvaluationControlService
from knowledge_platform.application.identity_provisioning import IdentityProvisioningService
from knowledge_platform.application.knowledge_ingestion import (
    KnowledgeIngestionService,
    KnowledgeSourceProcessingService,
)
from knowledge_platform.application.knowledge_sources import KnowledgeSourceService
from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderConfigurationResolver,
    ProviderConfigurationService,
)
from knowledge_platform.application.provider_usage import ProviderUsageService
from knowledge_platform.application.security_context import current_user_id
from knowledge_platform.application.system_conversations import SystemConversationService
from knowledge_platform.application.workspaces import WorkspaceService
from knowledge_platform.config.database import PlatformDatabaseSettings
from knowledge_platform.config.runtime import RuntimeSettings
from knowledge_platform.infrastructure.auth.supabase import SupabaseAuthAdapter
from knowledge_platform.infrastructure.auth.supabase_admin import SupabaseIdentityAdminAdapter
from knowledge_platform.infrastructure.credentials.environment import EnvironmentCredentialResolver
from knowledge_platform.infrastructure.documents.artifacts import FilesystemOriginalArtifactStore
from knowledge_platform.infrastructure.documents.parsers import parser_for_suffix
from knowledge_platform.infrastructure.embeddings.remote import RemoteEmbeddingAdapter
from knowledge_platform.infrastructure.evaluation.catalog import FilesystemSuiteCatalog
from knowledge_platform.infrastructure.evaluation.execution import (
    AssistantEvaluationExecutionFactory,
    ConversationManagementPort,
)
from knowledge_platform.infrastructure.evaluation.store import SqlAlchemyEvaluationStore
from knowledge_platform.infrastructure.models.remote import RemoteModelAdapter
from knowledge_platform.infrastructure.persistence.access_control import (
    AccessControlService,
)
from knowledge_platform.infrastructure.persistence.administration import (
    AdministrationService,
)
from knowledge_platform.infrastructure.persistence.commercial import CommercialService
from knowledge_platform.infrastructure.persistence.database import (
    create_platform_engine,
    create_session_factory,
)
from knowledge_platform.infrastructure.persistence.identity_provisioning import (
    SqlAlchemyIdentityProvisioningStore,
)
from knowledge_platform.infrastructure.persistence.ingestion_transactions import (
    SqlAlchemyWorkspaceTransactionRunner,
)
from knowledge_platform.infrastructure.persistence.repositories import (
    AssistantKnowledgeSourceRepository,
    AssistantRepository,
    ConversationRepository,
    KnowledgeSourceRepository,
    MessageRepository,
    SystemConversationRepository,
    WorkspaceRepository,
)
from knowledge_platform.infrastructure.persistence.system_conversations import (
    SqlAlchemySystemConversationControl,
)
from knowledge_platform.infrastructure.persistence.workspace_context import workspace_session_scope
from knowledge_platform.infrastructure.persistence.workspace_operational_state import (
    WorkspaceOperationalStateService,
)
from knowledge_platform.infrastructure.provider_configuration import (
    EnvironmentProviderConfiguration,
    RemoteProviderAdapterFactory,
    SqlAlchemyProviderConfigurationStore,
)
from knowledge_platform.infrastructure.provider_usage import OpenRouterUsageAdapter
from knowledge_platform.infrastructure.vector_search.postgres import (
    DocumentRepresentationRepository,
    PgvectorDocumentSearchAdapter,
)
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.conversation.domain.conversation import ConversationStatus
from knowledge_platform.modules.conversation.domain.identifiers import ConversationId
from knowledge_platform.modules.document_knowledge.artifacts import OriginalArtifact
from knowledge_platform.modules.document_knowledge.ports import VectorSearchPort
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
    KnowledgeSourceLifecycle,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.security import DataEgressPolicy
from knowledge_platform.modules.workspace_assistant.domain.workspace import (
    Workspace,
    WorkspaceOperationalStatus,
)


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    workspace: WorkspaceRepository
    assistant: AssistantRepository
    knowledge_source: KnowledgeSourceRepository
    representation: DocumentRepresentationRepository
    conversation: ConversationRepository
    message: MessageRepository
    assistant_sources: AssistantKnowledgeSourceRepository
    system_conversation: SystemConversationRepository


@dataclass(frozen=True, slots=True)
class ApplicationRuntime:
    settings: RuntimeSettings
    engine: Engine
    session_factory: sessionmaker[Session]
    credentials: EnvironmentCredentialResolver
    egress: DataEgressPolicy

    def access_control(self) -> AccessControlService:
        return AccessControlService(self.session_factory)

    def administration(self) -> AdministrationService:
        return AdministrationService(self.session_factory)

    def commercial(self) -> CommercialService:
        return CommercialService(self.session_factory)

    def provider_usage(self) -> ProviderUsageService:
        return ProviderUsageService(
            access=self.access_control(),
            telemetry=OpenRouterUsageAdapter(
                api_key=lambda: self.credentials.resolve(
                    self.settings.credential_for_model
                )
            ),
        )

    def environment_provider_configuration(self) -> EnvironmentProviderConfiguration:
        settings = self.settings
        return EnvironmentProviderConfiguration(
            generation_endpoint=settings.model_endpoint,
            generation_model=settings.model_reference,
            generation_credential_reference=settings.model_credential,
            embedding_endpoint=settings.embedding_endpoint,
            embedding_model=settings.embedding_model,
            embedding_credential_reference=settings.embedding_credential,
            embedding_dimensions=settings.embedding_dimensions,
        )

    def provider_configuration_store(self) -> SqlAlchemyProviderConfigurationStore:
        return SqlAlchemyProviderConfigurationStore(self.session_factory)

    def provider_configuration_resolver(self) -> ProviderConfigurationResolver:
        return ProviderConfigurationResolver(
            store=self.provider_configuration_store(),
            fallback=self.environment_provider_configuration(),
        )

    def provider_configuration(self) -> ProviderConfigurationService:
        store = self.provider_configuration_store()
        fallback = self.environment_provider_configuration()
        return ProviderConfigurationService(
            access=self.access_control(),
            resolver=ProviderConfigurationResolver(store=store, fallback=fallback),
            store=store,
            fallback=fallback,
        )

    def provider_adapter_factory(self) -> RemoteProviderAdapterFactory:
        return RemoteProviderAdapterFactory(
            resolver=self.provider_configuration_resolver(),
            credentials=self.credentials,
        )

    def system_conversations(self) -> SqlAlchemySystemConversationControl:
        return SqlAlchemySystemConversationControl(
            self.session_factory,
            self.access_control(),
            self.workspace_operational_state(),
            self.rag_service,
        )

    def workspace_operational_state(self) -> WorkspaceOperationalStateService:
        return WorkspaceOperationalStateService(self.session_factory)

    def auth_gateway(self) -> SupabaseAuthAdapter:
        if self.settings.supabase_auth_url is None or self.settings.supabase_publishable_key is None:
            raise RuntimeError("Supabase Auth configuration is incomplete")
        return SupabaseAuthAdapter(
            auth_url=self.settings.supabase_auth_url,
            publishable_key=self.settings.supabase_publishable_key.get_secret_value(),
        )

    def identity_provisioning(self) -> IdentityProvisioningService:
        if self.settings.supabase_auth_url is None:
            raise RuntimeError("Supabase Auth configuration is incomplete")
        admin_secret = (
            self.settings.supabase_secret_key.get_secret_value()
            if self.settings.supabase_secret_key is not None
            else None
        )
        return IdentityProvisioningService(
            access=self.access_control(),
            identity_admin=SupabaseIdentityAdminAdapter(
                auth_url=self.settings.supabase_auth_url,
                admin_secret=admin_secret,
            ),
            store=SqlAlchemyIdentityProvisioningStore(self.session_factory),
        )

    def repositories(self, session: Session) -> RepositoryBundle:
        return RepositoryBundle(
            workspace=WorkspaceRepository(session),
            assistant=AssistantRepository(session),
            knowledge_source=KnowledgeSourceRepository(session),
            representation=DocumentRepresentationRepository(session),
            conversation=ConversationRepository(session),
            message=MessageRepository(session),
            assistant_sources=AssistantKnowledgeSourceRepository(session),
            system_conversation=SystemConversationRepository(session),
        )

    def management_services(self) -> Any:
        runtime = self

        class Services:
            @staticmethod
            def _require_workspace_or_system(
                actor: UUID, workspace_id: UUID, workspace_permission: Permission,
                system_permission: Permission,
            ) -> None:
                try:
                    runtime.access_control().require_system(actor, system_permission)
                except AccessDenied:
                    runtime.access_control().require(actor, workspace_id, workspace_permission)

            @staticmethod
            def audit(
                session: Session, workspace_id: UUID, action: str,
                resource_type: str, resource_id: UUID | None,
                outcome: str = "succeeded", reason: str | None = None,
            ) -> None:
                if current_user_id() is None:
                    return
                session.execute(
                    text("""
                        select platform.append_audit_event(
                          :workspace,:action,:resource_type,:resource_id,
                          :outcome,'',jsonb_build_object(
                            'reason',cast(:reason as text)))
                    """),
                    {"workspace": workspace_id, "action": action,
                     "resource_type": resource_type, "resource_id": resource_id,
                     "outcome": outcome, "reason": reason},
                )

            @staticmethod
            def usage(
                session: Session, workspace_id: UUID, event_type: str,
                resource_type: str, resource_id: UUID,
            ) -> None:
                if current_user_id() is None:
                    return
                session.execute(
                    text("""
                        select platform.record_usage_event(
                          :workspace,:event_type,1,'operations',:resource_type,
                          :resource_id,'{}'::jsonb)
                    """),
                    {"workspace": workspace_id, "event_type": event_type,
                     "resource_type": resource_type, "resource_id": resource_id},
                )

            def create_workspace(
                self, name: str, *, ai_execution_enabled: bool = True
            ) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated System authority required for workspace creation")
                runtime.access_control().require_system(actor, Permission.WORKSPACE_MANAGE)
                value = Workspace.create(name=name).with_operational_state(
                    status=WorkspaceOperationalStatus.ACTIVE,
                    ai_execution_enabled=ai_execution_enabled,
                )
                with workspace_session_scope(runtime.session_factory, value.id) as session:
                    runtime.repositories(session).workspace.add(value)
                return value

            def get_workspace(self, workspace_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for workspace access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.WORKSPACE_READ,
                    Permission.SYSTEM_WORKSPACES_READ,
                )
                with workspace_session_scope(runtime.session_factory, WorkspaceId(workspace_id)) as session:
                    return WorkspaceService(runtime.repositories(session).workspace).get(WorkspaceId(workspace_id))

            def create_assistant(self, workspace_id: UUID, payload: Any) -> Any:
                wid = WorkspaceId(workspace_id)
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError(
                        "authenticated System authority required for Assistant creation"
                    )
                runtime.access_control().require_system(
                    actor, Permission.ASSISTANT_CREATE
                )
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    if WorkspaceService(runtime.repositories(session).workspace).get(wid) is None:
                        raise LookupError("workspace not found")
                    value = AssistantService(runtime.repositories(session).assistant).create(
                        workspace_id=wid, name=payload.name, description=payload.description,
                        instructions=payload.instructions, language=payload.language,
                        provider=payload.provider, model_reference=payload.model_reference,
                    )
                    self.audit(
                        session, workspace_id, "assistant.created", "assistant", value.id.value
                    )
                    return value

            def list_assistants(self, workspace_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for assistant access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.ASSISTANT_READ,
                    Permission.SYSTEM_ASSISTANTS_READ,
                )
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return AssistantService(runtime.repositories(session).assistant).list(wid)

            def get_assistant(self, workspace_id: UUID, assistant_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for assistant access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.ASSISTANT_READ,
                    Permission.SYSTEM_ASSISTANTS_READ,
                )
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return AssistantService(runtime.repositories(session).assistant).get(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id)
                    )

            def update_assistant(self, workspace_id: UUID, assistant_id: UUID, payload: Any) -> Any:
                wid = WorkspaceId(workspace_id)
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError(
                        "authenticated System authority required for Assistant update"
                    )
                runtime.access_control().require_system(
                    actor, Permission.ASSISTANT_UPDATE
                )
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    value = AssistantService(runtime.repositories(session).assistant).reconfigure(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id),
                        name=payload.name, description=payload.description,
                        instructions=payload.instructions, language=payload.language,
                        provider=payload.provider, model_reference=payload.model_reference,
                    )
                    return value

            def create_source(
                self,
                workspace_id: UUID,
                payload: Any,
                *,
                system_operation: bool = False,
            ) -> Any:
                wid = WorkspaceId(workspace_id)
                denial: str | None = None
                value: Any = None
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for source creation")
                if system_operation:
                    runtime.access_control().require_system(
                        actor, Permission.SYSTEM_KNOWLEDGE_CREATE
                    )
                else:
                    runtime.access_control().require(
                        actor, workspace_id, Permission.KNOWLEDGE_CREATE
                    )
                    runtime.administration().require_governance(
                        actor, workspace_id, "knowledge_source_addition_enabled"
                    )
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    if WorkspaceService(runtime.repositories(session).workspace).get(wid) is None:
                        raise LookupError("workspace not found")
                    current = session.execute(
                        text(
                            "select count(*) from platform.knowledge_sources where workspace_id=:workspace"
                        ),
                        {"workspace": workspace_id},
                    ).scalar_one()
                    denial = CommercialService.check_count_limit(
                        session, workspace_id, "max_knowledge_sources", int(current)
                    )
                    if denial:
                        self.audit(
                            session, workspace_id, "knowledge_source.create_denied",
                            "knowledge_source", None, "denied", denial,
                        )
                    else:
                        value = KnowledgeSourceService(
                            runtime.repositories(session).knowledge_source
                        ).register(
                            workspace_id=wid, name=payload.name,
                            kind=KnowledgeSourceKind(payload.kind),
                        )
                        self.audit(
                            session, workspace_id, "knowledge_source.created",
                            "knowledge_source", value.id.value,
                        )
                if denial:
                    raise CommercialError(denial)
                return value

            def list_sources(self, workspace_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for source access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.KNOWLEDGE_READ,
                    Permission.SYSTEM_KNOWLEDGE_READ,
                )
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return KnowledgeSourceService(runtime.repositories(session).knowledge_source).list(wid)

            def get_source(self, workspace_id: UUID, source_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for source access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.KNOWLEDGE_READ,
                    Permission.SYSTEM_KNOWLEDGE_READ,
                )
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return KnowledgeSourceService(runtime.repositories(session).knowledge_source).get(
                        workspace_id=wid, source_id=KnowledgeSourceId(source_id)
                    )

            def get_source_artifact(self, workspace_id: UUID, source_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for source access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.KNOWLEDGE_READ,
                    Permission.SYSTEM_KNOWLEDGE_READ,
                )
                wid = WorkspaceId(workspace_id)
                sid = KnowledgeSourceId(source_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    source = runtime.repositories(session).knowledge_source.get(
                        source_id=sid, workspace_id=wid
                    )
                    if source is None:
                        raise LookupError("source not found")
                return runtime.artifact_store().get(workspace_id=wid, source_id=sid)

            async def upload_source(
                self,
                workspace_id: UUID,
                source_id: UUID,
                chunks: AsyncIterator[bytes],
                filename: str,
                media_type: str | None,
                *,
                system_operation: bool = False,
            ) -> OriginalArtifact:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError(
                        "authenticated identity required for source upload"
                    )
                if system_operation:
                    runtime.access_control().require_system(
                        actor, Permission.SYSTEM_KNOWLEDGE_CREATE
                    )
                else:
                    runtime.access_control().require(
                        actor, workspace_id, Permission.KNOWLEDGE_CREATE
                    )
                    runtime.administration().require_governance(
                        actor,
                        workspace_id,
                        "knowledge_source_addition_enabled",
                    )
                wid = WorkspaceId(workspace_id)
                sid = KnowledgeSourceId(source_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    source = runtime.repositories(session).knowledge_source.get(
                        source_id=sid, workspace_id=wid
                    )
                    if source is None:
                        raise LookupError("source not found")
                artifacts = runtime.artifact_store()
                if artifacts.get(workspace_id=wid, source_id=sid) is not None:
                    raise ValueError("source already has an original artifact")
                if source.lifecycle not in {
                    KnowledgeSourceLifecycle.REGISTERED,
                    KnowledgeSourceLifecycle.FAILED,
                    KnowledgeSourceLifecycle.READY,
                }:
                    raise ValueError(
                        "source lifecycle does not accept an original artifact"
                    )
                data: list[bytes] = []
                total = 0
                async for chunk in chunks:
                    total += len(chunk)
                    if total > runtime.settings.max_artifact_bytes:
                        raise ValueError("artifact exceeds maximum size")
                    data.append(chunk)
                return artifacts.store(
                    workspace_id=wid, source_id=sid, chunks=data,
                    filename=filename, media_type=media_type,
                    max_bytes=runtime.settings.max_artifact_bytes,
                )

            def process_source(
                self,
                workspace_id: UUID,
                source_id: UUID,
                *,
                system_operation: bool = False,
            ) -> Any:
                wid = WorkspaceId(workspace_id)
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError(
                        "authenticated identity required for AI execution"
                    )
                if system_operation:
                    runtime.access_control().require_system(
                        actor, Permission.SYSTEM_KNOWLEDGE_PROCESS
                    )
                else:
                    runtime.access_control().require(
                        actor, workspace_id, Permission.KNOWLEDGE_PROCESS
                    )
                    runtime.administration().require_governance(
                        actor, workspace_id, "knowledge_processing_enabled"
                    )
                runtime.workspace_operational_state().require_ai_execution(
                    actor, workspace_id
                )
                return runtime.source_processing_service().process(
                    workspace_id=wid,
                    source_id=KnowledgeSourceId(source_id),
                    embedding_profile=runtime.provider_configuration_resolver()
                    .resolve(ModelCapability.EMBEDDING)
                    .model_id,
                )

            def attach_source(self, workspace_id: UUID, assistant_id: UUID, source_id: UUID) -> None:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated System authority required for source binding")
                runtime.access_control().require_system(actor, Permission.KNOWLEDGE_ATTACH)
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
                    self.audit(
                        session, workspace_id, "assistant.source_attached", "assistant", assistant_id
                    )

            def detach_source(self, workspace_id: UUID, assistant_id: UUID, source_id: UUID) -> None:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated System authority required for source binding")
                runtime.access_control().require_system(actor, Permission.KNOWLEDGE_ATTACH)
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    runtime.assistant_scope_service(session).detach(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id),
                        source_id=KnowledgeSourceId(source_id),
                    )
                    self.audit(
                        session, workspace_id, "assistant.source_detached", "assistant", assistant_id
                    )

            def list_attached_sources(self, workspace_id: UUID, assistant_id: UUID) -> list[Any]:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated identity required for source access")
                self._require_workspace_or_system(
                    actor, workspace_id, Permission.KNOWLEDGE_READ,
                    Permission.SYSTEM_KNOWLEDGE_READ,
                )
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
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated Workspace authority required for conversation creation")
                runtime.access_control().require(actor, workspace_id, Permission.CONVERSATIONS_CREATE)
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).create(
                        workspace_id=wid, assistant_id=AssistantId(assistant_id)
                    )

            def get_conversation(self, workspace_id: UUID, conversation_id: UUID) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated Workspace authority required for conversation access")
                runtime.access_control().require(actor, workspace_id, Permission.CONVERSATIONS_READ)
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).get(
                        workspace_id=wid,
                        conversation_id=ConversationId(conversation_id),
                    )

            def list_conversations(
                self,
                workspace_id: UUID,
                assistant_id: UUID | None = None,
                conversation_status: ConversationStatus | None = ConversationStatus.ACTIVE,
            ) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated Workspace authority required for conversation access")
                runtime.access_control().require(actor, workspace_id, Permission.CONVERSATIONS_READ)
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).list(
                        workspace_id=wid,
                        assistant_id=(
                            AssistantId(assistant_id) if assistant_id is not None else None
                        ),
                        status=conversation_status,
                    )

            def rename_conversation(
                self, workspace_id: UUID, conversation_id: UUID, title: str
            ) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated Workspace authority required for conversation rename")
                runtime.access_control().require(actor, workspace_id, Permission.CONVERSATIONS_RENAME)
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).rename(
                        workspace_id=wid,
                        conversation_id=ConversationId(conversation_id),
                        title=title,
                    )

            def set_conversation_archived(
                self, workspace_id: UUID, conversation_id: UUID, archived: bool
            ) -> Any:
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError("authenticated Workspace authority required for conversation archive")
                runtime.access_control().require(actor, workspace_id, Permission.CONVERSATIONS_ARCHIVE)
                wid = WorkspaceId(workspace_id)
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    return runtime.conversation_service(session).set_archived(
                        workspace_id=wid,
                        conversation_id=ConversationId(conversation_id),
                        archived=archived,
                    )

            def ask_conversation(self, workspace_id: UUID, conversation_id: UUID, question: str) -> Any:
                wid = WorkspaceId(workspace_id)
                actor = current_user_id()
                if actor is None:
                    raise RuntimeError(
                        "authenticated identity required for AI execution"
                    )
                runtime.access_control().require(actor, workspace_id, Permission.CONVERSATIONS_CREATE)
                runtime.workspace_operational_state().require_ai_execution(
                    actor, workspace_id
                )
                with workspace_session_scope(runtime.session_factory, wid) as session:
                    value = runtime.conversation_service(session).ask(
                        workspace_id=wid,
                        conversation_id=ConversationId(conversation_id),
                        question=question,
                    )
                    self.usage(
                        session, workspace_id, "assistant.question", "conversation", conversation_id
                    )
                    return value

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

    def system_conversation_service(
        self, session: Session
    ) -> SystemConversationService:
        repos = self.repositories(session)
        return SystemConversationService(
            access=self.access_control(),
            repository=repos.system_conversation,
            workspaces=repos.workspace,
            assistants=repos.assistant,
            sources=repos.knowledge_source,
            associations=repos.assistant_sources,
            rag=self.rag_service(session),
        )

    def embedding_gateway(self) -> RemoteEmbeddingAdapter:
        return self.provider_adapter_factory().embedding()

    def model_gateway(self) -> RemoteModelAdapter:
        return self.provider_adapter_factory().generation()

    def ingestion_service(self) -> DocumentIngestionService:
        return DocumentIngestionService(
            embeddings=self.embedding_gateway(), egress=self.egress
        )

    def source_processing_service(self) -> KnowledgeSourceProcessingService:
        return KnowledgeSourceProcessingService(
            transactions=SqlAlchemyWorkspaceTransactionRunner(self.session_factory),
            ingestion=self.knowledge_ingestion_service(),
        )

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

    def evaluation_control(self) -> EvaluationControlService:
        return EvaluationControlService(
            access=self.access_control(),
            catalog=self.evaluation_catalog(),
            store=SqlAlchemyEvaluationStore(self.session_factory),
            execution_factory=AssistantEvaluationExecutionFactory(
                cast(ConversationManagementPort, self.management_services())
            ),
            workspace_state=self.workspace_operational_state(),
        )

    def rag_service(self, session: Session) -> DocumentRagService:
        return DocumentRagService(
            embeddings=self.embedding_gateway(),
            vectors=cast(VectorSearchPort, PgvectorDocumentSearchAdapter(session)),
            model=self.model_gateway(),
            egress=self.egress,
            max_retrieval_distance=self.settings.max_retrieval_distance,
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
