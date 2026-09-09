from pathlib import Path
from uuid import uuid4

import pytest

from knowledge_platform.application.system_conversations import SystemConversationService
from knowledge_platform.modules.access_control.domain import (
    BUILT_IN_ROLE_PERMISSIONS,
    MEMBER_PERMISSIONS,
    SYSTEM_ADMIN_PERMISSIONS,
    WORKSPACE_MANAGER_PERMISSIONS,
    BuiltInRole,
    Permission,
    PermissionScope,
    ScopedRoleAssignment,
    permission_definition,
)
from knowledge_platform.modules.conversation.domain.conversation import (
    Conversation,
    ConversationStatus,
)
from knowledge_platform.modules.system_conversation.domain import (
    SystemConversation,
    SystemConversationStatus,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import (
    Workspace,
    WorkspaceOperationalStatus,
)

ROOT = Path(__file__).parents[2]
MIGRATION = (
    ROOT
    / "supabase/migrations/20260906070000_stage1_authority_data_foundation.sql"
)
STAGE7A_MIGRATION = (
    ROOT / "supabase/migrations/20260904184807_stage7a_identity_access_control.sql"
)
ACCESS = ROOT / "src/knowledge_platform/infrastructure/persistence/access_control.py"
ADMINISTRATION = (
    ROOT / "src/knowledge_platform/infrastructure/persistence/administration.py"
)
BOOTSTRAP = ROOT / "src/knowledge_platform/bootstrap/application.py"
PRODUCT_API = ROOT / "src/knowledge_platform/delivery/product_api.py"
SECURITY = ROOT / "src/knowledge_platform/delivery/security.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_permission_scope_is_canonical_and_scope_wins() -> None:
    workspace = uuid4()
    workspace_assignment = ScopedRoleAssignment(
        role_id=uuid4(),
        scope=PermissionScope.WORKSPACE,
        workspace_id=workspace,
        permissions=frozenset({Permission.WORKSPACE_READ, Permission.ROLES_MANAGE}),
    )
    assert workspace_assignment.allows(
        Permission.WORKSPACE_READ,
        requested_scope=PermissionScope.WORKSPACE,
        workspace_id=workspace,
    )
    assert not workspace_assignment.allows(
        Permission.WORKSPACE_READ,
        requested_scope=PermissionScope.WORKSPACE,
        workspace_id=uuid4(),
    )
    assert not workspace_assignment.allows(
        Permission.ROLES_MANAGE,
        requested_scope=PermissionScope.WORKSPACE,
        workspace_id=workspace,
    )
    assert permission_definition(Permission.ROLES_MANAGE).scope is PermissionScope.SYSTEM
    with pytest.raises(ValueError, match="cannot carry a workspace"):
        ScopedRoleAssignment(
            role_id=uuid4(),
            scope=PermissionScope.SYSTEM,
            workspace_id=workspace,
            permissions=frozenset(),
        )


def test_final_built_in_roles_and_immutable_permission_sets_are_exact() -> None:
    assert set(BUILT_IN_ROLE_PERMISSIONS) == {
        BuiltInRole.SYSTEM_ADMIN,
        BuiltInRole.WORKSPACE_MANAGER,
        BuiltInRole.MEMBER,
    }
    assert all(
        permission_definition(permission).scope is PermissionScope.SYSTEM
        for permission in SYSTEM_ADMIN_PERMISSIONS
    )
    assert all(
        permission_definition(permission).scope is PermissionScope.WORKSPACE
        for permission in WORKSPACE_MANAGER_PERMISSIONS | MEMBER_PERMISSIONS
    )
    assert Permission.ASSISTANT_CREATE not in WORKSPACE_MANAGER_PERMISSIONS
    assert Permission.MEMBERS_MANAGE not in WORKSPACE_MANAGER_PERMISSIONS


def test_final_permission_catalogue_is_complete_scoped_and_non_elevating() -> None:
    assert len(Permission) == 58
    assert not permission_definition(Permission.SYSTEM_ACCESS_MANAGE).delegable
    assert permission_definition(Permission.SYSTEM_ACCESS_MANAGE).scope is PermissionScope.SYSTEM
    assert all(
        definition.resource and definition.action
        for definition in map(permission_definition, Permission)
    )


def test_legacy_role_cutover_is_non_elevating_and_historized() -> None:
    sql = source(MIGRATION)
    assert "legacy.canonical_key in ('OWNER','ADMIN')" in sql
    assert "target.canonical_key='WORKSPACE_MANAGER'" in sql
    assert "legacy.canonical_key='MEMBER' and target.id=legacy.id" in sql
    assert "legacy.canonical_key='VIEWER'" in sql
    assert "Legacy Viewer (read-only)" in sql
    assert "workspace_role_assignment_history" in sql
    assert "invitation_role_migration_history" in sql
    bootstrap = sql.split("Project-Control approved initial bootstrap", 1)[1].split(
        "STAGE1_SYSTEM_ADMIN_BOOTSTRAP", 1
    )[0]
    assert "from platform.roles" not in bootstrap
    assert "workspace_memberships" not in bootstrap


def test_role_cutover_preflights_constraints_and_expression_unique_index() -> None:
    stage7a = source(STAGE7A_MIGRATION)
    assert "create unique index roles_workspace_name_unique" in stage7a
    assert "on platform.roles (workspace_id, lower(name))" in stage7a
    assert "foreign key (role_id, workspace_id)" in stage7a

    sql = source(MIGRATION)
    preflight = sql.split("do $stage1_role_preflight$", 1)[1].split(
        "$stage1_role_preflight$;", 1
    )[0]
    for token in (
        "pg_catalog.pg_index",
        "pg_catalog.pg_get_indexdef",
        "roles_workspace_name_unique",
        "(workspace_id, lower(name))",
        "pg_catalog.pg_constraint",
        "pg_catalog.pg_get_constraintdef",
        "platform.workspace_memberships",
        "platform.invitations",
        "STAGE1_REQUIRES_ROLE_REFERENCE_CONSTRAINTS",
        "STAGE1_EXPECTS_EXACTLY_ONE_LEGACY_MEMBER_PER_WORKSPACE",
        "STAGE1_CANONICAL_ROLE_NAME_COLLISION",
        "STAGE1_INVALID_LEGACY_ROLE_REFERENCE",
    ):
        assert token in preflight
    assert "lower('WORKSPACE_MANAGER')" in preflight
    assert "lower('Legacy Viewer (read-only)')" in preflight


def test_existing_member_identity_is_reused_and_permissions_are_reconciled() -> None:
    sql = source(MIGRATION)
    cutover = sql.split("-- Workspace roles:", 1)[1].split(
        "-- Independent SYSTEM authority", 1
    )[0]
    assert "when is_system and name='MEMBER' then 'built_in'" in cutover
    assert "when is_system and name='MEMBER' then 'active'" in cutover
    assert "cross join (values ('WORKSPACE_MANAGER'),('MEMBER'))" not in cutover
    manager_creation = cutover.split("insert into platform.roles(", 1)[1].split(
        "insert into platform.roles(", 1
    )[0]
    assert "select gen_random_uuid(),workspace.id,'WORKSPACE_MANAGER'" in manager_creation
    assert "'MEMBER'" not in manager_creation
    assert "legacy.canonical_key='MEMBER' and target.id=legacy.id" in cutover
    assert "delete from platform.roles" not in cutover.lower()
    assert "update platform.roles\nset name" not in cutover.lower()
    assert "update platform.roles\nset role_kind" in cutover
    assert "set role_id=history.mapped_role_id" in cutover
    assert "delete from platform.workspace_memberships" not in cutover.lower()
    assert "delete from platform.invitations" not in cutover.lower()

    reconciled_permissions = cutover.split(
        "-- Reconcile the reused historical MEMBER identity", 1
    )[1]
    member_end = "where role.role_kind='built_in' and role.canonical_key='MEMBER';"
    member_permissions = reconciled_permissions[
        : reconciled_permissions.index(member_end) + len(member_end)
    ]
    assert "delete from platform.role_permissions assignment" in member_permissions
    assert "role.canonical_key='MEMBER'" in member_permissions
    for permission in (
        "workspace.read",
        "assistant.read",
        "knowledge.read",
        "conversations.read",
        "conversations.create",
        "conversations.rename",
        "conversations.archive",
        "members.read",
        "notifications.read",
    ):
        assert permission in member_permissions
    assert "evaluation.read" not in member_permissions


def test_workspace_manager_and_viewer_targets_are_collision_safe_and_unambiguous() -> None:
    sql = source(MIGRATION)
    cutover = sql.split("-- Workspace roles:", 1)[1].split(
        "-- Independent SYSTEM authority", 1
    )[0]
    targets = cutover.split("do $stage1_role_targets$", 1)[1].split(
        "$stage1_role_targets$;", 1
    )[0]
    assert "role.canonical_key='WORKSPACE_MANAGER'" in targets
    assert "role.canonical_key='MEMBER'" in targets
    assert "role.name='Legacy Viewer (read-only)'" in targets
    assert "<>1" in targets
    assert "STAGE1_CANONICAL_ROLE_TARGET_AMBIGUOUS" in targets
    assert "legacy.canonical_key in ('OWNER','ADMIN')" in cutover
    assert "legacy.canonical_key='VIEWER'" in cutover


def test_legacy_is_system_flag_never_becomes_system_authority() -> None:
    sql = source(MIGRATION)
    workspace_authorization = sql.split(
        "create or replace function platform.user_has_permission", 1
    )[1].split("create function platform.user_has_any_system_access", 1)[0]
    system_authorization = sql.split(
        "create function platform.user_has_system_permission", 1
    )[1].split("create function platform.assign_system_access", 1)[0]
    assert "permission.scope='WORKSPACE'" in workspace_authorization
    assert "role.is_system" not in workspace_authorization
    assert "platform.system_access_assignments" in system_authorization
    assert "platform.system_roles" in system_authorization
    assert "platform.workspace_memberships" not in system_authorization
    assert "from platform.roles" not in system_authorization


def test_initial_system_admin_is_explicit_and_not_workspace_derived() -> None:
    sql = source(MIGRATION)
    bootstrap = sql.split("Project-Control approved initial bootstrap", 1)[1].split(
        "-- ---------------------------------------------------------------------------", 1
    )[0]
    assert "from platform.user_profiles where status='active'" in bootstrap
    assert "candidate_count<>1" in bootstrap
    assert "STAGE1_SYSTEM_ADMIN_BOOTSTRAP_REQUIRES_ONE_ACTIVE_PROFILE" in bootstrap
    assert "system_access_assignments" in bootstrap
    assert "workspace_memberships" not in bootstrap


def test_system_access_is_independent_and_last_admin_is_protected() -> None:
    sql = source(MIGRATION)
    assert "create table platform.system_access_assignments" in sql
    assert "create table platform.system_roles" in sql
    assert "create function platform.revoke_system_access" in sql
    assert "LAST_SYSTEM_ADMIN_REQUIRED" in sql
    assert "active_administrators<=1" in sql
    assert "fake workspace" not in sql.lower()


def test_builtin_role_identity_and_permission_mutation_are_blocked() -> None:
    sql = source(MIGRATION)
    for token in (
        "BUILT_IN_OR_LEGACY_ROLE_IMMUTABLE",
        "BUILT_IN_ROLE_PERMISSIONS_IMMUTABLE",
        "SYSTEM_BUILT_IN_ROLE_IMMUTABLE",
        "SYSTEM_BUILT_IN_PERMISSIONS_IMMUTABLE",
    ):
        assert token in sql
    assert "role_kind='custom'" in source(ACCESS)


def test_workspace_manager_and_member_never_gain_system_scope() -> None:
    assert not any(
        permission_definition(permission).scope is PermissionScope.SYSTEM
        for permission in WORKSPACE_MANAGER_PERMISSIONS | MEMBER_PERMISSIONS
    )
    sql = source(MIGRATION)
    user_has_permission = sql.split(
        "create or replace function platform.user_has_permission", 1
    )[1].split("create function platform.user_has_any_system_access", 1)[0]
    assert "permission.scope='WORKSPACE'" in user_has_permission
    assert "role.status='active'" in user_has_permission


def test_teams_are_not_an_authorization_scope() -> None:
    domain = source(
        ROOT / "src/knowledge_platform/modules/access_control/domain.py"
    )
    assert "TEAM" not in domain.split("class PermissionScope", 1)[1].split(
        "class RoleKind", 1
    )[0]
    assert "team_members" not in source(MIGRATION).split(
        "create or replace function platform.user_has_permission", 1
    )[1].split("create function platform.user_has_any_system_access", 1)[0]


def test_assistant_is_owned_by_exactly_one_workspace_and_creation_is_system_only() -> None:
    models = source(ROOT / "src/knowledge_platform/infrastructure/persistence/models.py")
    assert "class AssistantRecord" in models
    assert "workspace_id: Mapped[UUID]" in models
    assert "AssistantWorkspace" not in models
    assert "require_system(request.state.user.id, Permission.ASSISTANT_CREATE)" in source(
        PRODUCT_API
    )
    sql = source(MIGRATION)
    assistant_policy = sql.split("create policy assistants_runtime_insert", 1)[1].split(
        "create policy assistants_runtime_update", 1
    )[0]
    assert "user_has_system_permission('assistant.create')" in assistant_policy
    assert "user_has_permission" not in assistant_policy


def test_assistant_creation_policy_and_quota_are_retired_without_data_deletion() -> None:
    sql = source(MIGRATION)
    assert "set is_active=false where setting_key='assistant_creation_enabled'" in sql
    assert "drop trigger if exists stage7c_assistant_limit_before_insert" in sql
    create_assistant = source(BOOTSTRAP).split("def create_assistant", 1)[1].split(
        "def list_assistants", 1
    )[0]
    assert "assistant_creation_enabled" not in create_assistant
    assert "max_assistants" not in create_assistant
    assert "delete from platform.governance_settings" not in sql.lower()
    assert "delete from platform.plan_entitlements" not in sql.lower()


def test_transition_services_recheck_authority_and_policy_below_delivery() -> None:
    bootstrap = source(BOOTSTRAP)
    create_assistant = bootstrap.split("def create_assistant", 1)[1].split(
        "def list_assistants", 1
    )[0]
    create_source = bootstrap.split("def create_source", 1)[1].split(
        "def list_sources", 1
    )[0]
    process_source = bootstrap.split("def process_source", 1)[1].split(
        "def attach_source", 1
    )[0]
    assert "require_system" in create_assistant
    assert "Permission.ASSISTANT_CREATE" in create_assistant
    assert "Permission.KNOWLEDGE_CREATE" in create_source
    assert "knowledge_source_addition_enabled" in create_source
    assert "Permission.KNOWLEDGE_PROCESS" in process_source
    assert "knowledge_processing_enabled" in process_source


def test_final_knowledge_policies_are_fail_closed_and_enforced() -> None:
    product = source(PRODUCT_API)
    administration = source(ADMINISTRATION)
    sql = source(MIGRATION)
    assert "knowledge_source_addition_enabled" in product
    assert "knowledge_processing_enabled" in product
    assert "value is not None else False" in administration
    assert "knowledge_source_addition_enabled" in sql
    assert "knowledge_processing_enabled" in sql
    assert "setting_key='assistant_creation_enabled'" in sql


def test_workspace_operational_state_has_frozen_implication() -> None:
    suspended = Workspace.create(name="Workspace").with_operational_state(
        status=WorkspaceOperationalStatus.SUSPENDED,
        ai_execution_enabled=True,
    )
    assert suspended.operational_status is WorkspaceOperationalStatus.SUSPENDED
    assert not suspended.ai_execution_enabled
    active_without_ai = suspended.with_operational_state(
        status=WorkspaceOperationalStatus.ACTIVE,
        ai_execution_enabled=False,
    )
    assert active_without_ai.operational_status is WorkspaceOperationalStatus.ACTIVE
    assert not active_without_ai.ai_execution_enabled
    sql = source(MIGRATION)
    assert "workspaces_suspended_disables_ai" in sql
    assert "update_workspace_operational_state" in sql


def test_ai_execution_guards_precede_provider_backed_services() -> None:
    bootstrap = source(BOOTSTRAP)
    process = bootstrap.split("def process_source", 1)[1].split(
        "def attach_source", 1
    )[0]
    ask = bootstrap.split("def ask_conversation", 1)[1].split(
        "return Services()", 1
    )[0]
    assert process.index("require_ai_execution") < process.index(
        "source_processing_service"
    )
    assert ask.index("require_ai_execution") < ask.index("conversation_service")
    assert "authenticated identity required for AI execution" in process + ask
    evaluation = source(
        ROOT / "src/knowledge_platform/application/evaluation_control.py"
    )
    create_run = evaluation.split("def create_run", 1)[1].split(
        "def list_runs", 1
    )[0]
    assert "workspace_state: EvaluationWorkspaceStatePort" in evaluation
    assert "EvaluationWorkspaceStatePort | None" not in evaluation
    assert create_run.index("require_ai_execution") < create_run.index(
        "execution_factory.build"
    )


def test_workspace_conversation_lifecycle_is_non_destructive() -> None:
    conversation = Conversation.create_for_assistant(
        workspace_id=WorkspaceId(uuid4()), assistant_id=AssistantId(uuid4())
    )
    archived = conversation.archive()
    assert archived.id == conversation.id
    assert archived.status is ConversationStatus.ARCHIVED
    assert archived.restore().status is ConversationStatus.ACTIVE
    assert "def delete" not in source(
        ROOT / "src/knowledge_platform/application/assistant_conversations.py"
    )
    sql = source(MIGRATION).lower()
    assert "conversation '||substr(id::text,1,8)" in sql
    assert "delete from platform.conversations" not in sql
    assert "delete from platform.messages" not in sql
    assert "delete from platform.message_evidence" not in sql


def test_system_conversation_is_a_distinct_shared_system_aggregate() -> None:
    creator = uuid4()
    conversation = SystemConversation.create(title="System", created_by=creator)
    assert conversation.created_by == creator
    assert conversation.archive().status is SystemConversationStatus.ARCHIVED
    models = source(ROOT / "src/knowledge_platform/infrastructure/persistence/models.py")
    assert "class SystemConversationRecord" in models
    system_model = models.split("class SystemConversationRecord", 1)[1].split(
        "class DocumentRepresentationRecord", 1
    )[0]
    assert "workspace_id" not in system_model
    sql = source(MIGRATION)
    visibility = sql.split("create policy system_conversations_runtime_select", 1)[1].split(
        "create policy system_conversations_runtime_insert", 1
    )[0]
    assert "created_by" not in visibility
    assert "system_conversations.read" in visibility


def test_system_conversation_service_does_not_use_creator_as_visibility_scope() -> None:
    creator, reader = uuid4(), uuid4()
    conversation = SystemConversation.create(title="System", created_by=creator)

    class Access:
        calls: list[tuple[object, object]] = []

        def require_system(self, actor: object, permission: object) -> None:
            self.calls.append((actor, permission))

    class Repository:
        def get(self, conversation_id: object) -> SystemConversation | None:
            return conversation if conversation_id == conversation.id else None

    access = Access()
    service = SystemConversationService(access=access, repository=Repository())  # type: ignore[arg-type]
    assert service.get(reader, conversation.id) is conversation
    assert access.calls == [(reader, Permission.SYSTEM_CONVERSATIONS_READ)]


def test_system_conversation_permission_cannot_read_workspace_conversations() -> None:
    sql = source(MIGRATION)
    workspace_policy = sql.split("create policy conversations_runtime_select", 1)[1].split(
        "create policy conversations_runtime_insert", 1
    )[0]
    assert "conversations.read" in workspace_policy
    assert "system_conversations" not in workspace_policy
    assert "user_has_system_permission" not in workspace_policy


def test_evaluation_permissions_and_history_reconciliation() -> None:
    assert permission_definition(Permission.EVALUATION_READ).scope is PermissionScope.WORKSPACE
    assert permission_definition(Permission.EVALUATION_RUN).scope is PermissionScope.WORKSPACE
    assert Permission.EVALUATION_RUN in WORKSPACE_MANAGER_PERMISSIONS
    assert Permission.EVALUATION_RUN not in MEMBER_PERMISSIONS
    sql = source(MIGRATION).lower()
    assert "alter table evaluation.evaluation_runs" in sql
    assert "add column assistant_id uuid" in sql
    assert "add column requested_by uuid" in sql
    assert "evaluation_runs_assistant_workspace_fk" in sql
    assert "delete from evaluation.evaluation_runs" not in sql
    assert "delete from evaluation.evaluation_results" not in sql


def test_membership_team_and_invitation_mutations_are_system_authorized() -> None:
    access = source(ACCESS)
    for method in (
        "change_member_role",
        "remove_member",
        "save_team",
        "delete_team",
        "set_team_member",
        "create_invitation",
        "revoke_invitation",
    ):
        body = access.split(f"def {method}", 1)[1].split("\n    def ", 1)[0]
        assert "require_system" in body
    sql = source(MIGRATION)
    assert "user_has_system_permission('members.manage')" in sql
    assert "user_has_system_permission('invitations.manage')" in sql
    assert "user_has_system_permission('teams.manage')" in sql


def test_rls_grants_and_runtime_role_remain_fail_closed() -> None:
    sql = source(MIGRATION).lower()
    for table in (
        "workspace_role_assignment_history",
        "invitation_role_migration_history",
        "system_roles",
        "system_role_permissions",
        "system_access_assignments",
        "system_conversations",
        "system_conversation_messages",
    ):
        assert f"alter table platform.{table} enable row level security" in sql
        assert f"alter table platform.{table} force row level security" in sql
    assert "from anon,authenticated" in sql
    assert "alter role knowledge_platform_runtime" not in sql
    assert "from pg_catalog.pg_roles role" in sql
    assert "role.rolname='knowledge_platform_runtime'" in sql
    assert "role.rolcanlogin" in sql
    assert "not role.rolsuper" in sql
    assert "not role.rolcreatedb" in sql
    assert "not role.rolcreaterole" in sql
    assert "not role.rolbypassrls" in sql
    assert "stage1_runtime_role_security_precondition_failed" in sql
    assert "grant all" not in sql
    assert "grant delete on table platform.conversations" not in sql


def test_migration_has_no_destructive_product_cleanup_or_forbidden_schema_change() -> None:
    sql = source(MIGRATION).lower()
    for forbidden in (
        "drop table",
        "truncate",
        "delete from platform.workspaces",
        "delete from platform.assistants",
        "delete from platform.knowledge_sources",
        "delete from platform.teams",
        "alter extension",
        "create extension",
        "vector(",
    ):
        assert forbidden not in sql
