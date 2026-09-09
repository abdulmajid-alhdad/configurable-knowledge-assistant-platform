"""SQLAlchemy adapter for scoped identity, RBAC, and access administration."""
# ruff: noqa: E501

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import (
    AccessConflict,
    AccessDenied,
    AccessNotFound,
)
from knowledge_platform.modules.access_control.domain import (
    AuthenticatedUser,
    Permission,
    PermissionScope,
    permission_codes_for_scope,
    permission_definition,
)


class AccessControlService:
    """Uses parameterized SQL so security mutations share one DB transaction."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _rowcount(value: object) -> int:
        return cast(CursorResult[Any], value).rowcount

    @staticmethod
    def _audit(
        session: Session, workspace_id: UUID, action: str, resource_type: str,
        resource_id: UUID | None, metadata: dict[str, object] | None = None,
        outcome: str = "succeeded",
    ) -> None:
        session.execute(
            text("""
                select platform.append_audit_event(
                  :workspace,:action,:resource_type,:resource_id,:outcome,'',
                  cast(:metadata as jsonb))
            """),
            {"workspace": workspace_id, "action": action,
             "resource_type": resource_type, "resource_id": resource_id,
             "outcome": outcome, "metadata": json.dumps(metadata or {})},
        )

    @staticmethod
    def _check_limit(
        session: Session, workspace_id: UUID, entitlement: str, current_count: int
    ) -> str | None:
        value = session.execute(
            text("select platform.check_workspace_entitlement(:w,:key,:count)"),
            {"w": workspace_id, "key": entitlement, "count": current_count},
        ).scalar_one()
        return str(value) if value else None

    @contextmanager
    def _tx(self, user_id: UUID, workspace_id: UUID | None = None) -> Iterator[Session]:
        with self._sessions.begin() as session:
            session.execute(text("select set_config('app.user_id', :v, true)"), {"v": str(user_id)})
            # A transaction-local custom GUC becomes an empty string after a
            # pooled connection is reused. Existing forced-RLS policies cast
            # this value to UUID, so pre-selection operations need a valid,
            # deliberately non-authorizing workspace sentinel.
            session.execute(
                text("select set_config('app.workspace_id', :v, true)"),
                {"v": str(workspace_id or UUID(int=0))},
            )
            yield session

    def sync_profile(self, user: AuthenticatedUser) -> None:
        with self._tx(user.id) as session:
            session.execute(
                text("""
                insert into platform.user_profiles (user_id, email, display_name)
                values (:id, :email, :name)
                on conflict (user_id) do update set email=excluded.email,
                    display_name=coalesce(excluded.display_name, platform.user_profiles.display_name)
            """),
                {"id": user.id, "email": user.email, "name": user.display_name},
            )

    def discover_workspaces(self, user_id: UUID) -> list[dict[str, object]]:
        with self._tx(user_id) as session:
            memberships = session.execute(
                text("""
                select w.id, w.name, m.role_id
                from platform.workspace_memberships m
                join platform.workspaces w on w.id=m.workspace_id
                where m.user_id=:user and m.status='active'
                order by lower(w.name),w.id
            """),
                {"user": user_id},
            ).mappings().all()

            discovered: list[dict[str, object]] = []
            for membership in memberships:
                workspace_id = cast(UUID, membership["id"])
                session.execute(
                    text("select set_config('app.workspace_id', :v, true)"),
                    {"v": str(workspace_id)},
                )
                role = session.execute(
                    text("""
                    select r.id role_id, r.name role_name,
                           coalesce(array_agg(rp.permission_key order by rp.permission_key)
                             filter (where rp.permission_key is not null), '{}') permissions
                    from platform.roles r
                    left join platform.role_permissions rp on rp.role_id=r.id
                    where r.id=:role and r.workspace_id=:workspace
                      and r.status='active'
                    group by r.id,r.name
                """),
                    {"role": membership["role_id"], "workspace": workspace_id},
                ).mappings().one()
                discovered.append(
                    {
                        "id": workspace_id,
                        "name": membership["name"],
                        "role_id": role["role_id"],
                        "role_name": role["role_name"],
                        "permissions": role["permissions"],
                    }
                )
            return discovered

    def list_workspaces(self, actor: UUID) -> list[dict[str, object]]:
        self.require_system(actor, Permission.SYSTEM_WORKSPACES_READ)
        with self._tx(actor) as session:
            rows = session.execute(
                text("""
                    select id,name,operational_status,ai_execution_enabled
                    from platform.workspaces
                    order by lower(name),id
                """)
            ).mappings().all()
            can_read_settings = bool(
                session.execute(
                    text("select platform.user_has_system_permission('settings.read')")
                ).scalar_one()
            )
            result: list[dict[str, object]] = []
            for row in rows:
                workspace = cast(UUID, row["id"])
                item = dict(row)
                if can_read_settings:
                    session.execute(
                        text("select set_config('app.workspace_id', :v, true)"),
                        {"v": str(workspace)},
                    )
                    display_name = session.execute(
                        text(
                            "select display_name from platform.workspace_settings "
                            "where workspace_id=:workspace"
                        ),
                        {"workspace": workspace},
                    ).scalar_one_or_none()
                    if isinstance(display_name, str) and display_name.strip():
                        item["name"] = display_name
                result.append(item)
            return result

    def permissions(self, user_id: UUID, workspace_id: UUID) -> frozenset[str]:
        with self._tx(user_id, workspace_id) as session:
            values = session.execute(
                text("""
                select rp.permission_key from platform.workspace_memberships m
                join platform.roles r on r.id=m.role_id and r.workspace_id=m.workspace_id
                join platform.role_permissions rp on rp.role_id=m.role_id
                join platform.permissions p on p.key=rp.permission_key
                where m.workspace_id=:workspace and m.user_id=:user and m.status='active'
                  and r.status='active' and p.scope='WORKSPACE' and p.is_active
            """),
                {"workspace": workspace_id, "user": user_id},
            ).scalars()
            return frozenset(values)

    def require(self, user_id: UUID, workspace_id: UUID, permission: Permission) -> None:
        definition = permission_definition(permission)
        if definition.scope is not PermissionScope.WORKSPACE or not definition.active:
            raise AccessDenied("workspace scope cannot exercise this permission")
        available = self.permissions(user_id, workspace_id)
        if not available:
            raise AccessNotFound("workspace not found")
        if permission.value not in available:
            raise AccessDenied("permission denied")

    def system_permissions(self, user_id: UUID) -> frozenset[str]:
        with self._tx(user_id) as session:
            values = session.execute(
                text("""
                    select distinct rp.permission_key
                    from platform.system_access_assignments assignment
                    join platform.system_roles role on role.id=assignment.role_id
                    join platform.system_role_permissions rp on rp.role_id=role.id
                    join platform.permissions permission on permission.key=rp.permission_key
                    where assignment.user_id=:user and assignment.status='active'
                      and role.status='active' and permission.scope='SYSTEM'
                      and permission.is_active
                """),
                {"user": user_id},
            ).scalars()
            return frozenset(values)

    def require_system(self, user_id: UUID, permission: Permission) -> None:
        definition = permission_definition(permission)
        if definition.scope is not PermissionScope.SYSTEM or not definition.active:
            raise AccessDenied("system scope cannot exercise this permission")
        with self._tx(user_id) as session:
            allowed = bool(
                session.execute(
                    text("select platform.user_has_system_permission(:permission)"),
                    {"permission": permission.value},
                ).scalar_one()
            )
        if not allowed:
            raise AccessDenied("system permission denied")

    def _require_workspace_or_system(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        workspace_permission: Permission,
        system_permission: Permission,
    ) -> None:
        try:
            self.require_system(user_id, system_permission)
        except AccessDenied:
            self.require(user_id, workspace_id, workspace_permission)

    def list_system_access(self, actor: UUID) -> list[dict[str, object]]:
        self.require_system(actor, Permission.SYSTEM_ACCESS_READ)
        with self._tx(actor) as session:
            rows = session.execute(
                text("""
                    select assignment.user_id,profile.email,profile.display_name,
                           role.id role_id,role.name role_name,role.role_kind,
                           assignment.status,assignment.assigned_by,
                           assignment.created_at
                    from platform.system_access_assignments assignment
                    join platform.system_roles role on role.id=assignment.role_id
                    join platform.user_profiles profile on profile.user_id=assignment.user_id
                    order by lower(profile.email::text),role.name
                """)
            ).mappings()
            return [dict(row) for row in rows]

    def list_users(self, actor: UUID) -> list[dict[str, object]]:
        self.require_system(actor, Permission.SYSTEM_ACCESS_READ)
        with self._tx(actor) as session:
            rows = session.execute(
                text("""
                    select user_id,email,display_name,status,created_at
                    from platform.user_profiles
                    where status='active'
                    order by lower(email::text),user_id
                """)
            ).mappings()
            return [dict(row) for row in rows]

    def list_system_roles(self, actor: UUID) -> list[dict[str, object]]:
        self.require_system(actor, Permission.ROLES_READ)
        with self._tx(actor) as session:
            rows = session.execute(
                text("""
                    select role.id,role.name,role.role_kind,role.status,
                      coalesce(array_agg(permission_key order by permission_key)
                        filter (where permission_key is not null),'{}') permissions
                    from platform.system_roles role
                    left join platform.system_role_permissions assignment
                      on assignment.role_id=role.id
                    where role.status='active'
                    group by role.id order by role.role_kind,lower(role.name)
                """)
            ).mappings()
            return [dict(row) for row in rows]

    def create_system_role(
        self, actor: UUID, name: str, permissions: list[str]
    ) -> UUID:
        self.require_system(actor, Permission.ROLES_MANAGE)
        allowed = permission_codes_for_scope(
            PermissionScope.SYSTEM, delegable_only=True
        )
        if not permissions or not set(permissions) <= allowed:
            raise AccessDenied("custom system role permissions rejected")
        role_id = uuid4()
        with self._tx(actor) as session:
            session.execute(
                text("""
                    insert into platform.system_roles(
                      id,name,role_kind,is_builtin,status
                    ) values(:id,:name,'custom',false,'active')
                """),
                {"id": role_id, "name": name.strip()},
            )
            session.execute(
                text("""
                    insert into platform.system_role_permissions(role_id,permission_key)
                    select :id,unnest(:permissions)
                """),
                {"id": role_id, "permissions": permissions},
            )
        return role_id

    def update_system_role(
        self,
        actor: UUID,
        role_id: UUID,
        name: str,
        permissions: list[str],
    ) -> None:
        self.require_system(actor, Permission.ROLES_MANAGE)
        allowed = permission_codes_for_scope(
            PermissionScope.SYSTEM, delegable_only=True
        )
        if not permissions or not set(permissions) <= allowed:
            raise AccessDenied("custom system role permissions rejected")
        with self._tx(actor) as session:
            changed = self._rowcount(
                session.execute(
                    text("""
                        update platform.system_roles set name=:name
                        where id=:id and role_kind='custom'
                          and is_builtin=false and status='active'
                    """),
                    {"id": role_id, "name": name.strip()},
                )
            )
            if changed != 1:
                raise AccessNotFound("custom system role not found")
            session.execute(
                text("delete from platform.system_role_permissions where role_id=:id"),
                {"id": role_id},
            )
            session.execute(
                text("""
                    insert into platform.system_role_permissions(role_id,permission_key)
                    select :id,unnest(:permissions)
                """),
                {"id": role_id, "permissions": permissions},
            )

    def delete_system_role(self, actor: UUID, role_id: UUID) -> None:
        self.require_system(actor, Permission.ROLES_MANAGE)
        with self._tx(actor) as session:
            try:
                changed = self._rowcount(
                    session.execute(
                        text("""
                            delete from platform.system_roles
                            where id=:id and role_kind='custom'
                              and is_builtin=false and status='active'
                        """),
                        {"id": role_id},
                    )
                )
            except Exception:
                raise AccessConflict("system role is in use") from None
            if changed != 1:
                raise AccessNotFound("custom system role not found")

    def assign_system_access(self, actor: UUID, user_id: UUID, role_id: UUID) -> None:
        self.require_system(actor, Permission.SYSTEM_ACCESS_MANAGE)
        with self._tx(actor) as session:
            changed = session.execute(
                text("select platform.assign_system_access(:user,:role)"),
                {"user": user_id, "role": role_id},
            ).scalar_one()
            if not changed:
                raise AccessNotFound("system user or role not found")

    def revoke_system_access(self, actor: UUID, user_id: UUID, role_id: UUID) -> None:
        self.require_system(actor, Permission.SYSTEM_ACCESS_MANAGE)
        with self._tx(actor) as session:
            try:
                changed = session.execute(
                    text("select platform.revoke_system_access(:user,:role)"),
                    {"user": user_id, "role": role_id},
                ).scalar_one()
            except Exception:
                raise AccessConflict("system access revocation rejected") from None
            if not changed:
                raise AccessNotFound("system access assignment not found")

    def create_workspace(
        self,
        user_id: UUID,
        name: str,
        *,
        ai_execution_enabled: bool = True,
    ) -> dict[str, object]:
        self.require_system(user_id, Permission.WORKSPACE_MANAGE)
        if not ai_execution_enabled:
            self.require_system(user_id, Permission.GOVERNANCE_MANAGE)
        workspace_id = uuid4()
        with self._tx(user_id) as session:
            session.execute(
                text("select platform.create_workspace_stage1(:id,:name)"),
                {"id": workspace_id, "name": name.strip()},
            )
            session.execute(
                text("select set_config('app.workspace_id', :v, true)"),
                {"v": str(workspace_id)},
            )
            if not ai_execution_enabled:
                changed = bool(
                    session.execute(
                        text(
                            "select platform.update_workspace_operational_state"
                            "(:workspace,'ACTIVE',:ai_enabled)"
                        ),
                        {
                            "workspace": workspace_id,
                            "ai_enabled": ai_execution_enabled,
                        },
                    ).scalar_one()
                )
                if not changed:
                    raise AccessConflict("workspace operational state rejected")
            self._audit(session, workspace_id, "workspace.created", "workspace", workspace_id)
        return {
            "id": workspace_id,
            "name": name.strip(),
            "operational_status": "ACTIVE",
            "ai_execution_enabled": ai_execution_enabled,
        }

    def update_workspace(
        self,
        actor: UUID,
        workspace_id: UUID,
        *,
        name: str,
        operational_status: str,
        ai_execution_enabled: bool,
    ) -> dict[str, object]:
        self.require_system(actor, Permission.WORKSPACE_MANAGE)
        self.require_system(actor, Permission.GOVERNANCE_MANAGE)
        self.require_system(actor, Permission.WORKSPACE_SETTINGS_MANAGE)
        self.require_system(actor, Permission.SETTINGS_READ)
        if operational_status not in {"ACTIVE", "SUSPENDED"}:
            raise AccessConflict("workspace operational status rejected")
        normalized_name = name.strip()
        if not normalized_name:
            raise AccessConflict("workspace name rejected")
        effective_ai = ai_execution_enabled and operational_status != "SUSPENDED"
        with self._tx(actor, workspace_id) as session:
            settings = session.execute(
                text("""
                    select locale,timezone,commercial_contact
                    from platform.workspace_settings
                    where workspace_id=:workspace
                """),
                {"workspace": workspace_id},
            ).mappings().one_or_none()
            if settings is None:
                raise AccessNotFound("workspace not found")
            session.execute(
                text(
                    "select platform.update_workspace_settings"
                    "(:workspace,:name,:locale,:timezone,:contact)"
                ),
                {
                    "workspace": workspace_id,
                    "name": normalized_name,
                    "locale": settings["locale"],
                    "timezone": settings["timezone"],
                    "contact": settings["commercial_contact"],
                },
            )
            state_updated = bool(
                session.execute(
                    text(
                        "select platform.update_workspace_operational_state"
                        "(:workspace,:status,:ai_enabled)"
                    ),
                    {
                        "workspace": workspace_id,
                        "status": operational_status,
                        "ai_enabled": effective_ai,
                    },
                ).scalar_one()
            )
            if not state_updated:
                raise AccessConflict("workspace operational state rejected")
            self._audit(
                session,
                workspace_id,
                "workspace.updated",
                "workspace",
                workspace_id,
                {
                    "operational_status": operational_status,
                    "ai_execution_enabled": effective_ai,
                },
            )
        return {
            "id": workspace_id,
            "name": normalized_name,
            "operational_status": operational_status,
            "ai_execution_enabled": effective_ai,
        }

    def create_role(
        self, actor: UUID, workspace_id: UUID, name: str, permissions: list[str]
    ) -> UUID:
        self.require_system(actor, Permission.ROLES_MANAGE)
        allowed = permission_codes_for_scope(
            PermissionScope.WORKSPACE, delegable_only=True
        )
        if not set(permissions) <= allowed:
            raise AccessDenied("custom role permissions rejected")
        role_id = uuid4()
        denial: str | None = None
        with self._tx(actor, workspace_id) as session:
            current = int(session.execute(text(
                "select count(*) from platform.roles where workspace_id=:w "
                "and role_kind='custom' and status='active'"
            ), {"w": workspace_id}).scalar_one())
            denial = self._check_limit(
                session, workspace_id, "max_custom_roles", current
            )
            if denial:
                self._audit(
                    session, workspace_id, "role.create_denied", "role", None,
                    {"reason": denial}, "denied",
                )
            else:
                session.execute(
                    text("""
                        insert into platform.roles(
                          id,workspace_id,name,is_system,role_kind,status
                        ) values(:id,:w,:n,false,'custom','active')
                    """),
                    {"id": role_id, "w": workspace_id, "n": name.strip()},
                )
                session.execute(
                    text(
                        "insert into platform.role_permissions(role_id,permission_key) select :id,unnest(:permissions)"
                    ),
                    {"id": role_id, "permissions": permissions},
                )
                self._audit(session, workspace_id, "role.created", "role", role_id)
        if denial:
            raise AccessConflict(denial)
        return role_id

    def update_role(
        self, actor: UUID, workspace_id: UUID, role_id: UUID, name: str, permissions: list[str]
    ) -> None:
        self.require_system(actor, Permission.ROLES_MANAGE)
        allowed = permission_codes_for_scope(
            PermissionScope.WORKSPACE, delegable_only=True
        )
        if not set(permissions) <= allowed:
            raise AccessDenied("custom role permissions rejected")
        with self._tx(actor, workspace_id) as session:
            changed = self._rowcount(
                session.execute(
                    text(
                        "update platform.roles set name=:n where id=:id and workspace_id=:w "
                        "and role_kind='custom' and status='active'"
                    ),
                    {"n": name.strip(), "id": role_id, "w": workspace_id},
                )
            )
            if changed != 1:
                raise AccessNotFound("custom role not found")
            session.execute(
                text("delete from platform.role_permissions where role_id=:id"), {"id": role_id}
            )
            session.execute(
                text(
                    "insert into platform.role_permissions(role_id,permission_key) select :id,unnest(:permissions)"
                ),
                {"id": role_id, "permissions": permissions},
            )
            self._audit(session, workspace_id, "role.updated", "role", role_id)

    def delete_role(self, actor: UUID, workspace_id: UUID, role_id: UUID) -> None:
        self.require_system(actor, Permission.ROLES_MANAGE)
        with self._tx(actor, workspace_id) as session:
            try:
                changed = self._rowcount(
                    session.execute(
                        text(
                            "delete from platform.roles where id=:id and workspace_id=:w "
                            "and role_kind='custom' and status='active'"
                        ),
                        {"id": role_id, "w": workspace_id},
                    )
                )
            except Exception:
                raise AccessConflict("role is in use") from None
            if changed != 1:
                raise AccessNotFound("custom role not found")
            self._audit(session, workspace_id, "role.deleted", "role", role_id)

    def list_roles(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self.require_system(user_id, Permission.ROLES_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(
                text("""
                select r.id,r.name,r.is_system,r.role_kind,r.status,
                  'WORKSPACE'::text as canonical_scope,r.created_at,
                  count(distinct m.user_id) member_count,
                  coalesce(array_agg(rp.permission_key order by rp.permission_key)
                    filter(where rp.permission_key is not null),'{}') permissions
                from platform.roles r left join platform.role_permissions rp on rp.role_id=r.id
                left join platform.workspace_memberships m on m.role_id=r.id
                where r.workspace_id=:workspace and r.status='active'
                group by r.id order by r.is_system desc,r.name
            """),
                {"workspace": workspace_id},
            ).mappings()
            return [dict(row) for row in rows]

    def list_members(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._require_workspace_or_system(
            user_id,
            workspace_id,
            workspace_permission=Permission.MEMBERS_READ,
            system_permission=Permission.SYSTEM_MEMBERSHIPS_READ,
        )
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(
                text("""
                select p.user_id,p.email,p.display_name,m.status,m.created_at,m.joined_at,
                       r.id role_id,r.name role_name,
                       coalesce((
                         select array_agg(team.name order by lower(team.name))
                         from platform.team_members assignment
                         join platform.teams team
                           on team.id=assignment.team_id
                          and team.workspace_id=assignment.workspace_id
                         where assignment.workspace_id=m.workspace_id
                           and assignment.user_id=m.user_id
                       ),'{}') team_names
                from platform.workspace_memberships m join platform.user_profiles p on p.user_id=m.user_id
                join platform.roles r on r.id=m.role_id and r.workspace_id=m.workspace_id
                where m.workspace_id=:workspace order by lower(p.email::text)
            """),
                {"workspace": workspace_id},
            ).mappings()
            return [dict(row) for row in rows]

    def change_member_role(self, actor: UUID, workspace_id: UUID, member: UUID, role: UUID) -> None:
        self.require_system(actor, Permission.MEMBERS_MANAGE)
        try:
            with self._tx(actor, workspace_id) as session:
                result = session.execute(
                    text("select platform.change_membership_role(:workspace,:member,:role)"),
                    {"workspace": workspace_id, "member": member, "role": role},
                ).scalar_one()
                if not result:
                    raise AccessNotFound("member or role not found")
                self._audit(
                    session, workspace_id, "member.role_changed", "membership", member,
                    {"role_id": str(role)},
                )
        except AccessNotFound:
            raise
        except Exception:
            raise AccessConflict("membership role change rejected") from None

    def remove_member(self, actor: UUID, workspace_id: UUID, member: UUID) -> None:
        self.require_system(actor, Permission.MEMBERS_MANAGE)
        try:
            with self._tx(actor, workspace_id) as session:
                removed = session.execute(
                    text("select platform.remove_workspace_member(:workspace,:member)"),
                    {"workspace": workspace_id, "member": member},
                ).scalar_one()
                if not removed:
                    raise AccessNotFound("member not found")
                self._audit(session, workspace_id, "member.removed", "membership", member)
        except AccessNotFound:
            raise
        except Exception:
            raise AccessConflict("membership removal rejected") from None

    def list_teams(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self.require_system(user_id, Permission.TEAMS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(
                text("""
              select t.id,t.workspace_id,t.name,t.description,t.created_at,
                coalesce(
                  (select array_agg(tm.user_id order by tm.user_id)
                   from platform.team_members tm
                   where tm.team_id=t.id and tm.workspace_id=t.workspace_id),
                  '{}'
                ) member_ids
              from platform.teams t
              where t.workspace_id=:workspace order by lower(t.name)
            """),
                {"workspace": workspace_id},
            ).mappings()
            return [dict(row) for row in rows]

    def save_team(
        self,
        actor: UUID,
        workspace_id: UUID,
        name: str,
        description: str | None,
        team_id: UUID | None = None,
    ) -> UUID:
        self.require_system(actor, Permission.TEAMS_MANAGE)
        value = team_id or uuid4()
        denial: str | None = None
        with self._tx(actor, workspace_id) as session:
            workspace_exists = bool(
                session.execute(
                    text(
                        "select exists(select 1 from platform.workspaces "
                        "where id=:workspace)"
                    ),
                    {"workspace": workspace_id},
                ).scalar_one()
            )
            if not workspace_exists:
                raise AccessNotFound("workspace not found")
            if team_id is None:
                current = int(session.execute(
                    text("select count(*) from platform.teams where workspace_id=:w"),
                    {"w": workspace_id},
                ).scalar_one())
                denial = self._check_limit(session, workspace_id, "max_teams", current)
                if denial:
                    self._audit(
                        session, workspace_id, "team.create_denied", "team", None,
                        {"reason": denial}, "denied",
                    )
                else:
                    session.execute(
                        text(
                            "insert into platform.teams(id,workspace_id,name,description) values(:id,:w,:n,:d)"
                        ),
                        {"id": value, "w": workspace_id, "n": name.strip(), "d": description},
                    )
            else:
                result = session.execute(
                    text(
                        "update platform.teams set name=:n,description=:d where id=:id and workspace_id=:w"
                    ),
                    {"id": value, "w": workspace_id, "n": name.strip(), "d": description},
                )
                if self._rowcount(result) != 1:
                    raise AccessNotFound("team not found")
            if not denial:
                self._audit(
                    session, workspace_id,
                    "team.created" if team_id is None else "team.updated", "team", value,
                )
        if denial:
            raise AccessConflict(denial)
        return value

    def delete_team(self, actor: UUID, workspace_id: UUID, team_id: UUID) -> None:
        self.require_system(actor, Permission.TEAMS_MANAGE)
        with self._tx(actor, workspace_id) as session:
            if (
                self._rowcount(
                    session.execute(
                        text("delete from platform.teams where id=:id and workspace_id=:w"),
                        {"id": team_id, "w": workspace_id},
                    )
                )
                != 1
            ):
                raise AccessNotFound("team not found")
            self._audit(session, workspace_id, "team.deleted", "team", team_id)

    def set_team_member(
        self, actor: UUID, workspace_id: UUID, team_id: UUID, member_id: UUID, present: bool
    ) -> None:
        self.require_system(actor, Permission.TEAMS_MANAGE)
        with self._tx(actor, workspace_id) as session:
            team_exists = bool(
                session.execute(
                    text(
                        "select exists(select 1 from platform.teams "
                        "where id=:team and workspace_id=:workspace)"
                    ),
                    {"team": team_id, "workspace": workspace_id},
                ).scalar_one()
            )
            member_exists = bool(
                session.execute(
                    text(
                        "select exists(select 1 from platform.workspace_memberships "
                        "where workspace_id=:workspace and user_id=:member "
                        "and (not cast(:present as boolean) or status='active'))"
                    ),
                    {
                        "workspace": workspace_id,
                        "member": member_id,
                        "present": present,
                    },
                ).scalar_one()
            )
            if not team_exists or not member_exists:
                raise AccessNotFound("team or workspace member not found")
            if present:
                session.execute(
                    text(
                        "insert into platform.team_members(team_id,workspace_id,user_id) values(:t,:w,:u) on conflict do nothing"
                    ),
                    {"t": team_id, "w": workspace_id, "u": member_id},
                )
            else:
                session.execute(
                    text(
                        "delete from platform.team_members where team_id=:t and workspace_id=:w and user_id=:u"
                    ),
                    {"t": team_id, "w": workspace_id, "u": member_id},
                )
            self._audit(
                session, workspace_id,
                "team.member_added" if present else "team.member_removed", "team", team_id,
                {"member_id": str(member_id)},
            )

    def list_invitations(self, actor: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self.require_system(actor, Permission.INVITATIONS_READ)
        with self._tx(actor, workspace_id) as session:
            rows = session.execute(
                text("""
              select i.id,i.email,i.provisioned_user_id,i.team_id,
                case when i.status='pending' and i.expires_at<=now() then 'expired' else i.status end status,
                i.created_at,i.expires_at,r.id role_id,r.name role_name,
                     p.display_name inviter_name,p.email inviter_email,
                     provisioned.display_name provisioned_display_name,
                     team.name team_name
              from platform.invitations i join platform.roles r on r.id=i.role_id
              join platform.user_profiles p on p.user_id=i.invited_by
              left join platform.user_profiles provisioned
                on provisioned.user_id=i.provisioned_user_id
              left join platform.teams team
                on team.id=i.team_id and team.workspace_id=i.workspace_id
              where i.workspace_id=:workspace order by i.created_at desc
            """),
                {"workspace": workspace_id},
            ).mappings()
            return [dict(row) for row in rows]

    def revoke_invitation(self, actor: UUID, workspace_id: UUID, invitation_id: UUID) -> None:
        self.require_system(actor, Permission.INVITATIONS_MANAGE)
        with self._tx(actor, workspace_id) as session:
            changed = session.execute(
                text("select platform.revoke_invitation(:workspace,:invitation)"),
                {"workspace": workspace_id, "invitation": invitation_id},
            ).scalar_one()
            if not changed:
                raise AccessConflict("invitation is not pending")
            self._audit(
                session, workspace_id, "invitation.revoked", "invitation", invitation_id,
            )
