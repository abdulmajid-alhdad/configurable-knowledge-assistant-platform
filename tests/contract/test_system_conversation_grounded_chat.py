"""Focused contracts for grounded System Assistant conversations."""

from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import AccessControlPort, AccessDenied
from knowledge_platform.application.document_rag import DocumentRagService
from knowledge_platform.application.system_conversations import (
    SystemConversationConflict,
    SystemConversationService,
)
from knowledge_platform.application.workspace_operational_state import (
    WorkspaceAIExecutionDisabled,
    WorkspaceOperationalStatePort,
    WorkspaceSuspended,
)
from knowledge_platform.infrastructure.persistence import (
    system_conversations as persistence,
)
from knowledge_platform.infrastructure.persistence.system_conversations import (
    SqlAlchemySystemConversationControl,
)
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.conversation.domain.message import MessageOutcome
from knowledge_platform.modules.evidence_grounding.domain.contracts import (
    Evidence,
    GroundedAnswer,
)
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import (
    KnowledgeSource,
)
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
)
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260910101500_system_conversation_grounded_chat.sql"
LOCK_MIGRATION = (
    ROOT / "supabase/migrations/20260910114500_system_conversation_execution_lock.sql"
)
STAGE1_MIGRATION = (
    ROOT / "supabase/migrations/20260906070000_stage1_authority_data_foundation.sql"
)


class Access:
    def __init__(self) -> None:
        self.calls: list[Permission] = []
        self.denied: Permission | None = None

    def require_system(self, _actor: UUID, permission: Permission) -> None:
        self.calls.append(permission)
        if permission is self.denied:
            raise AccessDenied("permission denied")


class Conversations:
    def __init__(self) -> None:
        self.values: dict[UUID, SystemConversation] = {}

    def add(self, conversation: SystemConversation) -> None:
        self.values[conversation.id] = conversation

    def get(self, conversation_id: UUID) -> SystemConversation | None:
        return self.values.get(conversation_id)

    def get_for_update(self, conversation_id: UUID) -> SystemConversation | None:
        return self.get(conversation_id)

    def list(self, *, status: SystemConversationStatus | None = None) -> list[SystemConversation]:
        return [
            item for item in self.values.values()
            if status is None or item.status is status
        ]

    def rename(self, conversation_id: UUID, title: str) -> SystemConversation | None:
        current = self.get(conversation_id)
        if current is None:
            return None
        changed = current.rename(title)
        self.add(changed)
        return changed

    def set_archived(
        self, conversation_id: UUID, archived: bool
    ) -> SystemConversation | None:
        current = self.get(conversation_id)
        if current is None:
            return None
        changed = current.archive() if archived else current.restore()
        self.add(changed)
        return changed

    def add_message(self, conversation: SystemConversation) -> None:
        self.add(conversation)


class Assistants:
    def __init__(self, value: Assistant) -> None:
        self.value = value

    def get(self, *, assistant_id: AssistantId, workspace_id: WorkspaceId) -> Assistant | None:
        if (assistant_id, workspace_id) == (self.value.id, self.value.workspace_id):
            return self.value
        return None


class Workspaces:
    def __init__(self, value: Workspace) -> None:
        self.value = value

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        return self.value if workspace_id == self.value.id else None


class Sources:
    def __init__(self, value: KnowledgeSource) -> None:
        self.value = value

    def list_for_workspace(self, workspace_id: WorkspaceId) -> list[KnowledgeSource]:
        return [self.value] if workspace_id == self.value.workspace_id else []


class Associations:
    def __init__(self, assistant: Assistant, source: KnowledgeSource) -> None:
        self.assistant = assistant
        self.source = source

    def list_source_ids(
        self, *, assistant_id: AssistantId, workspace_id: WorkspaceId
    ) -> frozenset:
        if (assistant_id, workspace_id) != (self.assistant.id, self.assistant.workspace_id):
            return frozenset()
        return frozenset({self.source.id})


class Rag:
    def __init__(self, outcome: GroundedAnswer) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def ask(self, **kwargs: object) -> GroundedAnswer:
        self.calls.append(kwargs)
        return self.outcome


class MetadataService:
    def __init__(self, workspace_id: WorkspaceId, conversation: SystemConversation) -> None:
        self.workspace_id = workspace_id
        self.conversation = conversation
        self.execution_calls = 0

    def execution_workspace(self, _actor: UUID, _conversation_id: UUID) -> WorkspaceId:
        self.execution_calls += 1
        return self.workspace_id

    def get(self, _actor: UUID, _conversation_id: UUID) -> SystemConversation:
        return self.conversation


class DenyingWorkspaceState:
    def __init__(self, error: WorkspaceSuspended | WorkspaceAIExecutionDisabled) -> None:
        self.error = error
        self.calls: list[tuple[UUID, UUID]] = []

    def require_ai_execution(self, actor: UUID, workspace_id: UUID) -> None:
        self.calls.append((actor, workspace_id))
        raise self.error


@contextmanager
def memory_session_scope(_sessions: object):
    yield object()


def bound_conversation(workspace_id: WorkspaceId) -> SystemConversation:
    return SystemConversation.create(
        title="Bound system conversation",
        created_by=uuid4(),
        workspace_id=workspace_id,
        assistant_id=AssistantId(uuid4()),
    )


def configured_service() -> tuple[
    SystemConversationService,
    Conversations,
    Access,
    Workspace,
    Assistant,
    KnowledgeSource,
    Rag,
]:
    workspace = Workspace.create(name="System target")
    assistant = Assistant.create(
        workspace_id=workspace.id,
        name="Grounded assistant",
        description=None,
        instructions="Use only evidence.",
        language="ar",
        model_configuration=ModelConfiguration("configured", "configured"),
        retrieval_configuration=RetrievalConfiguration(),
    )
    source = KnowledgeSource.create(
        workspace_id=workspace.id,
        name="Eligible source",
        kind=KnowledgeSourceKind.DOCUMENT,
    ).begin_preparation().mark_ready()
    rag = Rag(
        GroundedAnswer(
            answer="Grounded result",
            evidence=(Evidence(source.id, "Supported content", "source#1"),),
        )
    )
    access = Access()
    conversations = Conversations()
    return (
        SystemConversationService(
            access=access,
            repository=conversations,
            workspaces=Workspaces(workspace),
            assistants=Assistants(assistant),
            sources=Sources(source),
            associations=Associations(assistant, source),
            rag=rag,
        ),
        conversations,
        access,
        workspace,
        assistant,
        source,
        rag,
    )


def test_system_chat_is_bound_grounded_and_persists_evidence() -> None:
    service, conversations, access, workspace, assistant, source, rag = configured_service()
    actor = uuid4()
    conversation = service.create(
        actor,
        workspace_id=workspace.id,
        assistant_id=assistant.id,
        title="System grounded chat",
    )

    outcome = service.ask(actor, conversation.id, question="What is supported?")
    reloaded = conversations.get(conversation.id)

    assert outcome.answer == "Grounded result"
    assert reloaded is not None
    assert reloaded.workspace_id == workspace.id
    assert reloaded.assistant_id == assistant.id
    assert [message.role.value for message in reloaded.messages] == ["user", "assistant"]
    assert reloaded.messages[-1].outcome is MessageOutcome.GROUNDED
    assert reloaded.messages[-1].evidence[0].source_id == source.id
    assert rag.calls[0]["assistant_instructions"] == assistant.instructions
    assert rag.calls[0]["source_ids"] == frozenset({source.id})
    assert Permission.SYSTEM_CONVERSATIONS_CREATE in access.calls
    assert Permission.SYSTEM_KNOWLEDGE_READ in access.calls


def test_system_conversation_ask_reraises_access_denied_to_global_403_handler() -> None:
    delivery = (ROOT / "src/knowledge_platform/delivery/system_conversation_api.py").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "src/knowledge_platform/delivery/app.py").read_text(encoding="utf-8")
    ask_handler = delivery.split('@router.post("/{conversation_id}/ask")', 1)[1]

    assert "except AccessDenied:\n            raise" in ask_handler
    assert ask_handler.index("except AccessDenied") < ask_handler.index("except Exception")
    assert "@application.exception_handler(AccessDenied)" in app
    assert 'JSONResponse({"detail": "permission denied"}, status_code=403)' in app


def test_system_conversation_ask_propagates_missing_system_permission() -> None:
    service, _conversations, access, _workspace, _assistant, _source, rag = (
        configured_service()
    )
    access.denied = Permission.SYSTEM_CONVERSATIONS_READ

    with pytest.raises(AccessDenied):
        service.ask(uuid4(), uuid4(), question="Denied")

    assert rag.calls == []


@pytest.mark.parametrize(
    "error",
    [WorkspaceSuspended(), WorkspaceAIExecutionDisabled()],
)
def test_system_ask_checks_workspace_hard_gate_before_constructing_rag(
    monkeypatch: pytest.MonkeyPatch,
    error: WorkspaceSuspended | WorkspaceAIExecutionDisabled,
) -> None:
    workspace_id = WorkspaceId(uuid4())
    conversation = bound_conversation(workspace_id)
    metadata = MetadataService(workspace_id, conversation)
    workspace_state = DenyingWorkspaceState(error)
    rag_factory_calls: list[object] = []
    workspace_session_calls: list[WorkspaceId] = []

    def rag_factory(session: object) -> Rag:
        rag_factory_calls.append(session)
        raise AssertionError("RAG must not be constructed before the hard gate")

    @contextmanager
    def workspace_scope(_sessions: object, selected_workspace: WorkspaceId):
        workspace_session_calls.append(selected_workspace)
        yield object()

    control = SqlAlchemySystemConversationControl(
        cast(sessionmaker[Session], object()),
        cast(AccessControlPort, object()),
        cast(WorkspaceOperationalStatePort, workspace_state),
        cast(Callable[[Session], DocumentRagService], rag_factory),
    )
    monkeypatch.setattr(persistence, "system_session_scope", memory_session_scope)
    monkeypatch.setattr(persistence, "workspace_session_scope", workspace_scope)
    monkeypatch.setattr(control, "_service", lambda _session: metadata)

    with pytest.raises(type(error)):
        control.ask(uuid4(), conversation.id, question="Do not execute")

    assert metadata.execution_calls == 1
    assert workspace_state.calls
    assert rag_factory_calls == []
    assert workspace_session_calls == []
    assert conversation.messages == ()


def test_system_conversation_read_does_not_construct_rag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = WorkspaceId(uuid4())
    conversation = bound_conversation(workspace_id)
    metadata = MetadataService(workspace_id, conversation)
    rag_factory_calls: list[object] = []

    def rag_factory(session: object) -> Rag:
        rag_factory_calls.append(session)
        raise AssertionError("read must not construct RAG")

    control = SqlAlchemySystemConversationControl(
        cast(sessionmaker[Session], object()),
        cast(AccessControlPort, object()),
        cast(WorkspaceOperationalStatePort, object()),
        cast(Callable[[Session], DocumentRagService], rag_factory),
    )
    monkeypatch.setattr(persistence, "system_session_scope", memory_session_scope)
    monkeypatch.setattr(control, "_service", lambda _session: metadata)

    assert control.get(uuid4(), conversation.id) == conversation
    assert rag_factory_calls == []


def test_legacy_unbound_system_conversation_is_readable_but_cannot_ask() -> None:
    service, conversations, _access, _workspace, _assistant, _source, rag = configured_service()
    now = datetime.now(UTC)
    legacy = SystemConversation(
        id=uuid4(),
        title="Legacy",
        status=SystemConversationStatus.ACTIVE,
        created_by=uuid4(),
        workspace_id=None,
        assistant_id=None,
        messages=(),
        created_at=now,
        updated_at=now,
    )
    conversations.add(legacy)

    with pytest.raises(SystemConversationConflict, match="legacy and unbound"):
        service.ask(uuid4(), legacy.id, question="Should not execute")

    assert rag.calls == []


def test_system_conversation_migration_preserves_legacy_and_system_only_evidence() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "(workspace_id is null) = (assistant_id is null)" in sql
    assert "references platform.assistants(id,workspace_id)" in sql
    assert "system_conversation_message_evidence" in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "platform.user_has_system_permission('system_knowledge.read')" in sql
    assert "platform.user_has_workspace_membership" not in sql
    assert "platform.conversations" not in sql


def test_system_conversation_read_policies_require_bound_resource_visibility() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    conversation_select = sql.split(
        "create policy system_conversations_runtime_select", 1
    )[1].split("drop policy if exists system_conversations_runtime_insert", 1)[0]
    evidence_select = sql.split(
        "create policy system_conversation_message_evidence_runtime_select", 1
    )[1].split("create policy system_conversation_message_evidence_runtime_insert", 1)[0]

    assert "drop policy if exists system_conversations_runtime_select" in sql
    assert "workspace_id is null" in conversation_select
    for permission in (
        "system_conversations.read",
        "system_workspaces.read",
        "system_assistants.read",
        "system_knowledge.read",
    ):
        assert f"platform.user_has_system_permission('{permission}')" in conversation_select
        assert f"platform.user_has_system_permission('{permission}')" in evidence_select
    assert "conversation.workspace_id is not null" in evidence_select
    assert "platform.user_has_workspace_membership" not in conversation_select
    assert "platform.user_has_workspace_membership" not in evidence_select
    assert "platform.user_has_permission(" not in conversation_select
    assert "platform.user_has_permission(" not in evidence_select


def test_system_execution_lock_is_protected_without_runtime_table_update() -> None:
    lock_sql = LOCK_MIGRATION.read_text(encoding="utf-8")
    stage1_sql = STAGE1_MIGRATION.read_text(encoding="utf-8")
    repository = (
        ROOT / "src/knowledge_platform/infrastructure/persistence/repositories.py"
    ).read_text(encoding="utf-8")
    lock_method = repository.split("def get_for_update(self, conversation_id: UUID)", 1)[
        1
    ].split("def list(", 1)[0]

    assert "security definer" in lock_sql
    assert "set search_path = ''" in lock_sql
    assert "for update" in lock_sql
    assert "update platform.system_conversations" not in lock_sql
    assert (
        "revoke all on function "
        "platform.lock_system_conversation_for_execution(uuid)" in lock_sql
    )
    assert "from public, anon, authenticated" in lock_sql
    assert (
        "grant execute on function "
        "platform.lock_system_conversation_for_execution(uuid)" in lock_sql
    )
    assert "to knowledge_platform_runtime" in lock_sql
    for permission in (
        "system_conversations.read",
        "system_conversations.create",
        "system_workspaces.read",
        "system_assistants.read",
        "system_knowledge.read",
    ):
        assert f"platform.user_has_system_permission('{permission}')" in lock_sql
    assert "platform.user_has_workspace_membership" not in lock_sql
    assert "platform.user_has_permission(" not in lock_sql
    assert "grant select,insert on platform.system_conversations," in stage1_sql
    assert "grant update on platform.system_conversations" not in stage1_sql
    assert "lock_system_conversation_for_execution" in lock_method
    assert ".with_for_update()" not in lock_method


def test_system_conversation_frontend_is_bound_chat_without_delete_or_direct_provider() -> None:
    frontend = (ROOT / "frontend/system/controls-pages.js").read_text(encoding="utf-8")
    delivery = (ROOT / "src/knowledge_platform/delivery/system_conversation_api.py").read_text(
        encoding="utf-8"
    )
    section = frontend.split("export function systemConversationsPage", 1)[1].split(
        "function auditDetails", 1
    )[0]
    assert "workspace_id" in section
    assert "/api/system/workspaces/${workspaceId}/assistants" in frontend
    assert "/ask" in frontend
    assert "محادثة قديمة غير مرتبطة بمساحة عمل ومساعد" in section
    assert "message.evidence" in frontend
    assert "const detailContent = [" in section
    detail_renderer = section.split("const detailContent = [", 1)[1].split(
        "detail.replaceChildren();", 1
    )[0]
    assert " : null" not in detail_renderer
    assert "if (legacy) {" in detail_renderer
    assert "detailContent.push(errorState(" in detail_renderer
    assert "detailContent.push(messages);" in detail_renderer
    assert 'if (!legacy && value.status === "ACTIVE" && can("system_conversations.create")) {' in detail_renderer
    assert "detailContent.push(systemConversationComposer(value, open));" in detail_renderer
    assert "appendContent(detail, detailContent);" in section
    assert 'method: "DELETE"' not in section
    assert "supabase" not in section.lower()
    assert "openrouter" not in section.lower()
    assert '"/{conversation_id}/ask"' in delivery
