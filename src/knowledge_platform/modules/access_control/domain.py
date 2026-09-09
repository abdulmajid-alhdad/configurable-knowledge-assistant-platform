"""Scoped Control Plane identity and authorization contracts.

Permission scope is canonical catalogue metadata. A role assignment can only
exercise permissions whose scope matches the assignment scope; possession of a
permission code never widens that boundary.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class MembershipStatus(StrEnum):
    ACTIVE = "active"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class PermissionScope(StrEnum):
    SYSTEM = "SYSTEM"
    WORKSPACE = "WORKSPACE"


class RoleKind(StrEnum):
    BUILT_IN = "built_in"
    CUSTOM = "custom"
    LEGACY = "legacy"


class RoleStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class BuiltInRole(StrEnum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    WORKSPACE_MANAGER = "WORKSPACE_MANAGER"
    MEMBER = "MEMBER"


class Permission(StrEnum):
    # Final Workspace permissions.
    WORKSPACE_READ = "workspace.read"
    ASSISTANT_READ = "assistant.read"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_CREATE = "knowledge.create"
    KNOWLEDGE_PROCESS = "knowledge.process"
    CONVERSATIONS_READ = "conversations.read"
    CONVERSATIONS_CREATE = "conversations.create"
    CONVERSATIONS_RENAME = "conversations.rename"
    CONVERSATIONS_ARCHIVE = "conversations.archive"
    EVALUATION_READ = "evaluation.read"
    EVALUATION_RUN = "evaluation.run"
    MEMBERS_READ = "members.read"
    NOTIFICATIONS_READ = "notifications.read"

    # Final System permissions. Some established codes are intentionally
    # retained: their canonical scope, rather than a name prefix, is decisive.
    SYSTEM_WORKSPACES_READ = "system_workspaces.read"
    WORKSPACE_MANAGE = "workspace.manage"
    SYSTEM_ASSISTANTS_READ = "system_assistants.read"
    ASSISTANT_CREATE = "assistant.create"
    ASSISTANT_UPDATE = "assistant.update"
    SYSTEM_ASSISTANTS_ASSIGN = "system_assistants.assign"
    SYSTEM_KNOWLEDGE_READ = "system_knowledge.read"
    SYSTEM_KNOWLEDGE_CREATE = "system_knowledge.create"
    SYSTEM_KNOWLEDGE_PROCESS = "system_knowledge.process"
    KNOWLEDGE_ATTACH = "knowledge.attach"
    SYSTEM_MEMBERSHIPS_READ = "system_memberships.read"
    MEMBERS_MANAGE = "members.manage"
    TEAMS_READ = "teams.read"
    TEAMS_MANAGE = "teams.manage"
    ROLES_READ = "roles.read"
    ROLES_MANAGE = "roles.manage"
    INVITATIONS_READ = "invitations.read"
    INVITATIONS_MANAGE = "invitations.manage"
    GOVERNANCE_READ = "governance.read"
    GOVERNANCE_MANAGE = "governance.manage"
    USAGE_READ = "usage.read"
    PROVIDERS_READ = "providers.read"
    PROVIDERS_MANAGE = "providers.manage"
    CREDENTIALS_READ = "credentials.read"
    CREDENTIALS_MANAGE = "credentials.manage"
    SYSTEM_CONVERSATIONS_READ = "system_conversations.read"
    SYSTEM_CONVERSATIONS_CREATE = "system_conversations.create"
    SYSTEM_CONVERSATIONS_RENAME = "system_conversations.rename"
    SYSTEM_CONVERSATIONS_ARCHIVE = "system_conversations.archive"
    AUDIT_READ = "audit.read"
    SYSTEM_ACCESS_READ = "system_access.read"
    SYSTEM_ACCESS_MANAGE = "system_access.manage"

    # Real internal/deferred administration capabilities retained from Stage
    # 7C. They remain System-scoped even while their UI is absent.
    OPERATIONS_READ = "operations.read"
    SETTINGS_READ = "settings.read"
    NOTIFICATIONS_MANAGE = "notifications.manage"
    PLANS_READ = "plans.read"
    SUBSCRIPTIONS_READ = "subscriptions.read"
    SUBSCRIPTIONS_MANAGE = "subscriptions.manage"
    API_KEYS_READ = "api_keys.read"
    API_KEYS_MANAGE = "api_keys.manage"
    SECURITY_READ = "security.read"
    SECURITY_MANAGE = "security.manage"
    WORKSPACE_SETTINGS_MANAGE = "workspace_settings.manage"

    # Historical permission identifiers. They remain readable for audit and
    # migration traceability, but are not active/delegable in the final model.
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_ASK = "conversation.ask"


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    permission: Permission
    scope: PermissionScope
    resource: str
    action: str
    active: bool = True
    delegable: bool = True


_WORKSPACE_PERMISSIONS = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.ASSISTANT_READ,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_CREATE,
        Permission.KNOWLEDGE_PROCESS,
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_CREATE,
        Permission.CONVERSATIONS_RENAME,
        Permission.CONVERSATIONS_ARCHIVE,
        Permission.EVALUATION_READ,
        Permission.EVALUATION_RUN,
        Permission.MEMBERS_READ,
        Permission.NOTIFICATIONS_READ,
    }
)

_HISTORICAL_PERMISSIONS = frozenset(
    {Permission.CONVERSATION_READ, Permission.CONVERSATION_ASK}
)

_NON_DELEGABLE_INTERNAL_PERMISSIONS = frozenset(
    {
        Permission.PLANS_READ,
        Permission.SUBSCRIPTIONS_READ,
        Permission.SUBSCRIPTIONS_MANAGE,
        Permission.API_KEYS_READ,
        Permission.API_KEYS_MANAGE,
        Permission.SYSTEM_ACCESS_MANAGE,
    }
)


def _permission_definition(permission: Permission) -> PermissionDefinition:
    namespace, action = permission.value.split(".", maxsplit=1)
    active = permission not in _HISTORICAL_PERMISSIONS
    return PermissionDefinition(
        permission=permission,
        scope=(
            PermissionScope.WORKSPACE
            if permission in _WORKSPACE_PERMISSIONS
            else PermissionScope.SYSTEM
        ),
        resource=namespace,
        action=action,
        active=active,
        delegable=active and permission not in _NON_DELEGABLE_INTERNAL_PERMISSIONS,
    )


PERMISSION_CATALOG = {
    permission: _permission_definition(permission) for permission in Permission
}


def permission_definition(permission: Permission) -> PermissionDefinition:
    return PERMISSION_CATALOG[permission]


def permission_codes_for_scope(
    scope: PermissionScope, *, delegable_only: bool = False
) -> frozenset[str]:
    return frozenset(
        definition.permission.value
        for definition in PERMISSION_CATALOG.values()
        if definition.scope is scope
        and definition.active
        and (definition.delegable or not delegable_only)
    )


WORKSPACE_MANAGER_PERMISSIONS = frozenset(
    definition.permission
    for definition in PERMISSION_CATALOG.values()
    if definition.scope is PermissionScope.WORKSPACE and definition.active
)

MEMBER_PERMISSIONS = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.ASSISTANT_READ,
        Permission.KNOWLEDGE_READ,
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_CREATE,
        Permission.CONVERSATIONS_RENAME,
        Permission.CONVERSATIONS_ARCHIVE,
        Permission.MEMBERS_READ,
        Permission.NOTIFICATIONS_READ,
    }
)

SYSTEM_ADMIN_PERMISSIONS = frozenset(
    definition.permission
    for definition in PERMISSION_CATALOG.values()
    if definition.scope is PermissionScope.SYSTEM and definition.active
)

BUILT_IN_ROLE_PERMISSIONS = {
    BuiltInRole.SYSTEM_ADMIN: SYSTEM_ADMIN_PERMISSIONS,
    BuiltInRole.WORKSPACE_MANAGER: WORKSPACE_MANAGER_PERMISSIONS,
    BuiltInRole.MEMBER: MEMBER_PERMISSIONS,
}

# Compatibility name for existing application imports while carrying only the
# final built-in identities.
SYSTEM_ROLE_PERMISSIONS = {
    role.value: permissions for role, permissions in BUILT_IN_ROLE_PERMISSIONS.items()
}


@dataclass(frozen=True, slots=True)
class ScopedRoleAssignment:
    role_id: UUID
    scope: PermissionScope
    permissions: frozenset[Permission]
    workspace_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.scope is PermissionScope.SYSTEM and self.workspace_id is not None:
            raise ValueError("system assignments cannot carry a workspace")
        if self.scope is PermissionScope.WORKSPACE and self.workspace_id is None:
            raise ValueError("workspace assignments require a workspace")

    def allows(
        self,
        permission: Permission,
        *,
        requested_scope: PermissionScope,
        workspace_id: UUID | None = None,
    ) -> bool:
        definition = permission_definition(permission)
        if not definition.active:
            return False
        if requested_scope is not self.scope or definition.scope is not self.scope:
            return False
        if self.scope is PermissionScope.WORKSPACE and workspace_id != self.workspace_id:
            return False
        return permission in self.permissions


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    email: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        normalized = self.email.strip().casefold()
        if not normalized or "@" not in normalized:
            raise ValueError("authenticated user email is invalid")
        object.__setattr__(self, "email", normalized)


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    workspace_id: UUID
    workspace_name: str
    role_id: UUID
    role_name: str
    permissions: frozenset[Permission]


@dataclass(frozen=True, slots=True)
class Member:
    user_id: UUID
    email: str
    display_name: str | None
    role_id: UUID
    role_name: str
    status: MembershipStatus
    created_at: datetime
    joined_at: datetime | None


@dataclass(frozen=True, slots=True)
class Role:
    id: UUID
    workspace_id: UUID
    name: str
    is_system: bool
    permissions: frozenset[Permission]
    member_count: int = 0
    kind: RoleKind = RoleKind.CUSTOM
    status: RoleStatus = RoleStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class Team:
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    member_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class Invitation:
    id: UUID
    workspace_id: UUID
    email: str
    role_id: UUID
    role_name: str
    invited_by: UUID
    expires_at: datetime
    status: InvitationStatus
    created_at: datetime

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(UTC)


class AuthenticationRequired(RuntimeError):
    """No valid application session exists."""


class PermissionDenied(RuntimeError):
    """The authenticated identity lacks the required scoped permission."""
