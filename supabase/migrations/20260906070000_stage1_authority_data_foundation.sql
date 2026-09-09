-- Stage 1: scoped authority, system access, Workspace operational state,
-- conversation lifecycle, System conversations, and Evaluation reconciliation.
-- Forward-only and data-preserving: applied Stage 7A/7B/7C artifacts remain immutable.

-- ---------------------------------------------------------------------------
-- Fail fast against the exact legacy role shape and the expression unique
-- index that governs every role name written by this cutover. The historical
-- MEMBER identity is reused below; no second MEMBER row may be manufactured.
-- The old is_system flag is used only to recognize Stage 7A legacy rows; it
-- never grants SYSTEM scope, which exists solely in the separate tables below.
-- ---------------------------------------------------------------------------
do $stage1_role_preflight$
begin
  if not exists(
    select 1
    from pg_catalog.pg_index index_metadata
    join pg_catalog.pg_class index_relation
      on index_relation.oid=index_metadata.indexrelid
    join pg_catalog.pg_class table_relation
      on table_relation.oid=index_metadata.indrelid
    join pg_catalog.pg_namespace table_namespace
      on table_namespace.oid=table_relation.relnamespace
    where table_namespace.nspname='platform'
      and table_relation.relname='roles'
      and index_relation.relname='roles_workspace_name_unique'
      and index_metadata.indisunique
      and pg_catalog.pg_get_indexdef(index_relation.oid)
        like '%(workspace_id, lower(name))%'
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_REQUIRES_ROLES_WORKSPACE_NAME_UNIQUE_INDEX';
  end if;

  if not exists(
    select 1 from pg_catalog.pg_constraint constraint_metadata
    where constraint_metadata.contype='f'
      and constraint_metadata.conrelid='platform.workspace_memberships'::regclass
      and constraint_metadata.confrelid='platform.roles'::regclass
      and pg_catalog.pg_get_constraintdef(constraint_metadata.oid)
        like 'FOREIGN KEY (role_id, workspace_id) REFERENCES platform.roles(id, workspace_id)%'
  ) or not exists(
    select 1 from pg_catalog.pg_constraint constraint_metadata
    where constraint_metadata.contype='f'
      and constraint_metadata.conrelid='platform.invitations'::regclass
      and constraint_metadata.confrelid='platform.roles'::regclass
      and pg_catalog.pg_get_constraintdef(constraint_metadata.oid)
        like 'FOREIGN KEY (role_id, workspace_id) REFERENCES platform.roles(id, workspace_id)%'
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_REQUIRES_ROLE_REFERENCE_CONSTRAINTS';
  end if;

  if exists(
    select 1
    from platform.workspaces workspace
    where (
      select count(*)
      from platform.roles role
      where role.workspace_id=workspace.id
        and role.is_system
        and role.name='MEMBER'
    )<>1
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_EXPECTS_EXACTLY_ONE_LEGACY_MEMBER_PER_WORKSPACE';
  end if;

  if exists(
    select 1
    from platform.workspaces workspace
    cross join (values ('OWNER'),('ADMIN'),('VIEWER')) expected(role_name)
    where (
      select count(*)
      from platform.roles role
      where role.workspace_id=workspace.id
        and role.is_system
        and role.name=expected.role_name
    )<>1
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_EXPECTS_ONE_OWNER_ADMIN_VIEWER_PER_WORKSPACE';
  end if;

  if exists(
    select 1 from platform.roles role
    where role.is_system
      and role.name not in ('OWNER','ADMIN','MEMBER','VIEWER')
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_UNEXPECTED_LEGACY_SYSTEM_ROLE';
  end if;

  if exists(
    select 1 from platform.roles role
    where lower(role.name) in (
      lower('WORKSPACE_MANAGER'),lower('Legacy Viewer (read-only)')
    )
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_CANONICAL_ROLE_NAME_COLLISION';
  end if;

  if exists(
    select 1
    from platform.workspace_memberships membership
    left join platform.roles role
      on role.id=membership.role_id
      and role.workspace_id=membership.workspace_id
    where role.id is null
  ) or exists(
    select 1
    from platform.invitations invitation
    left join platform.roles role
      on role.id=invitation.role_id
      and role.workspace_id=invitation.workspace_id
    where role.id is null
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_INVALID_LEGACY_ROLE_REFERENCE';
  end if;
end
$stage1_role_preflight$;

-- ---------------------------------------------------------------------------
-- Canonical permission catalogue: scope is authoritative and cannot be widened
-- by the role or assignment that contains a permission.
-- ---------------------------------------------------------------------------
alter table platform.permissions
  add column scope text,
  add column resource text,
  add column action text,
  add column is_active boolean not null default true,
  add column is_delegable boolean not null default true;

update platform.permissions
set scope = case
      when key in (
        'workspace.read','assistant.read','knowledge.read','knowledge.create',
        'knowledge.process','evaluation.read','members.read','notifications.read'
      ) then 'WORKSPACE'
      else 'SYSTEM'
    end,
    resource = split_part(key,'.',1),
    action = split_part(key,'.',2);

update platform.permissions
set is_active=false,is_delegable=false
where key in ('conversation.read','conversation.ask');

update platform.permissions
set is_delegable=false
where key in (
  'plans.read','subscriptions.read','subscriptions.manage',
  'api_keys.read','api_keys.manage','system_access.manage'
);

insert into platform.permissions(
  key,description,scope,resource,action,is_active,is_delegable
) values
  ('conversations.read','Read Workspace conversations','WORKSPACE','conversations','read',true,true),
  ('conversations.create','Create and use Workspace conversations','WORKSPACE','conversations','create',true,true),
  ('conversations.rename','Rename Workspace conversations','WORKSPACE','conversations','rename',true,true),
  ('conversations.archive','Archive or restore Workspace conversations','WORKSPACE','conversations','archive',true,true),
  ('evaluation.run','Run version-controlled Evaluation suites','WORKSPACE','evaluation','run',true,true),
  ('system_workspaces.read','Read Workspace administration records','SYSTEM','system_workspaces','read',true,true),
  ('system_assistants.read','Read Assistant administration records','SYSTEM','system_assistants','read',true,true),
  ('system_assistants.assign','Assign Assistants to Workspaces','SYSTEM','system_assistants','assign',true,true),
  ('system_knowledge.read','Read Knowledge administration records','SYSTEM','system_knowledge','read',true,true),
  ('system_knowledge.create','Create Knowledge Sources for a Workspace','SYSTEM','system_knowledge','create',true,true),
  ('system_knowledge.process','Process Knowledge Sources administratively','SYSTEM','system_knowledge','process',true,true),
  ('system_memberships.read','Read membership administration records','SYSTEM','system_memberships','read',true,true),
  ('system_conversations.read','Read System conversations','SYSTEM','system_conversations','read',true,true),
  ('system_conversations.create','Create and use System conversations','SYSTEM','system_conversations','create',true,true),
  ('system_conversations.rename','Rename System conversations','SYSTEM','system_conversations','rename',true,true),
  ('system_conversations.archive','Archive or restore System conversations','SYSTEM','system_conversations','archive',true,true),
  ('system_access.read','Read System access assignments','SYSTEM','system_access','read',true,true),
  ('system_access.manage','Manage System access assignments','SYSTEM','system_access','manage',true,false);

alter table platform.permissions
  alter column scope set not null,
  alter column resource set not null,
  alter column action set not null,
  add constraint permissions_scope_vocabulary check (scope in ('SYSTEM','WORKSPACE')),
  add constraint permissions_resource_nonblank check (btrim(resource)<>''),
  add constraint permissions_action_nonblank check (btrim(action)<>'');

-- ---------------------------------------------------------------------------
-- Workspace roles: legacy OWNER/ADMIN/VIEWER identities remain as immutable
-- historical rows, while the existing MEMBER identity is reconciled in place.
-- Active built-ins are exactly WORKSPACE_MANAGER and MEMBER. A generated
-- custom read-only role preserves legitimate Workspace VIEWER behavior.
-- ---------------------------------------------------------------------------
alter table platform.roles
  add column role_kind text,
  add column status text,
  add column canonical_key text;

update platform.roles
set role_kind=case
      when is_system and name='MEMBER' then 'built_in'
      when is_system then 'legacy'
      else 'custom'
    end,
    status=case
      when is_system and name='MEMBER' then 'active'
      when is_system then 'deprecated'
      else 'active'
    end,
    canonical_key=case when is_system then name else null end;

alter table platform.roles
  alter column role_kind set not null,
  alter column status set not null,
  add constraint roles_kind_vocabulary check (role_kind in ('built_in','custom','legacy')),
  add constraint roles_status_vocabulary check (status in ('active','deprecated')),
  add constraint roles_canonical_identity check (
    (role_kind in ('built_in','legacy') and canonical_key is not null)
    or (role_kind='custom' and canonical_key is null)
  );

insert into platform.roles(
  id,workspace_id,name,is_system,role_kind,status,canonical_key
)
select gen_random_uuid(),workspace.id,'WORKSPACE_MANAGER',true,
  'built_in','active','WORKSPACE_MANAGER'
from platform.workspaces workspace;

insert into platform.roles(
  id,workspace_id,name,is_system,role_kind,status,canonical_key
)
select gen_random_uuid(),workspace.id,'Legacy Viewer (read-only)',false,'custom','active',null
from platform.workspaces workspace;

do $stage1_role_targets$
begin
  if exists(
    select 1
    from platform.workspaces workspace
    where (
      select count(*) from platform.roles role
      where role.workspace_id=workspace.id and role.status='active'
        and role.role_kind='built_in'
        and role.canonical_key='WORKSPACE_MANAGER'
    )<>1
    or (
      select count(*) from platform.roles role
      where role.workspace_id=workspace.id and role.status='active'
        and role.role_kind='built_in' and role.canonical_key='MEMBER'
        and role.name='MEMBER'
    )<>1
    or (
      select count(*) from platform.roles role
      where role.workspace_id=workspace.id and role.status='active'
        and role.role_kind='custom'
        and role.name='Legacy Viewer (read-only)'
    )<>1
  ) then
    raise exception using errcode='P0001',
      message='STAGE1_CANONICAL_ROLE_TARGET_AMBIGUOUS';
  end if;
end
$stage1_role_targets$;

insert into platform.role_permissions(role_id,permission_key)
select role.id,permission.key
from platform.roles role
join platform.permissions permission
  on permission.scope='WORKSPACE' and permission.is_active
where role.role_kind='built_in' and role.canonical_key='WORKSPACE_MANAGER';

-- Reconcile the reused historical MEMBER identity to the exact final immutable
-- MEMBER permission set. Its UUID and every referencing row remain unchanged.
delete from platform.role_permissions assignment
using platform.roles role
where assignment.role_id=role.id
  and role.role_kind='built_in' and role.canonical_key='MEMBER';

insert into platform.role_permissions(role_id,permission_key)
select role.id,permission.key
from platform.roles role
join platform.permissions permission on permission.key in (
  'workspace.read','assistant.read','knowledge.read',
  'conversations.read','conversations.create','conversations.rename',
  'conversations.archive','members.read','notifications.read'
)
where role.role_kind='built_in' and role.canonical_key='MEMBER';

insert into platform.role_permissions(role_id,permission_key)
select role.id,permission.key
from platform.roles role
join platform.permissions permission on permission.key in (
  'workspace.read','assistant.read','knowledge.read','conversations.read',
  'evaluation.read','members.read','notifications.read'
)
where role.role_kind='custom' and role.name='Legacy Viewer (read-only)';

-- Preserve the nearest non-elevating semantics of existing custom roles.
insert into platform.role_permissions(role_id,permission_key)
select assignment.role_id,'conversations.read'
from platform.role_permissions assignment
join platform.roles role on role.id=assignment.role_id
where role.role_kind='custom' and assignment.permission_key='conversation.read'
on conflict do nothing;
insert into platform.role_permissions(role_id,permission_key)
select assignment.role_id,'conversations.create'
from platform.role_permissions assignment
join platform.roles role on role.id=assignment.role_id
where role.role_kind='custom' and assignment.permission_key='conversation.ask'
on conflict do nothing;

create table platform.workspace_role_assignment_history (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces(id),
  user_id uuid not null references auth.users(id),
  legacy_role_id uuid not null references platform.roles(id),
  legacy_role_name text not null,
  mapped_role_id uuid not null references platform.roles(id),
  mapped_role_name text not null,
  recorded_at timestamptz not null default now()
);
create index workspace_role_assignment_history_workspace_user_idx
  on platform.workspace_role_assignment_history(workspace_id,user_id,recorded_at desc);

insert into platform.workspace_role_assignment_history(
  workspace_id,user_id,legacy_role_id,legacy_role_name,mapped_role_id,mapped_role_name
)
select membership.workspace_id,membership.user_id,legacy.id,legacy.name,target.id,target.name
from platform.workspace_memberships membership
join platform.roles legacy on legacy.id=membership.role_id
  and (
    legacy.role_kind='legacy'
    or (legacy.role_kind='built_in' and legacy.canonical_key='MEMBER')
  )
join platform.roles target on target.workspace_id=membership.workspace_id
  and target.status='active'
  and (
    (legacy.canonical_key in ('OWNER','ADMIN')
      and target.canonical_key='WORKSPACE_MANAGER')
    or (legacy.canonical_key='MEMBER' and target.id=legacy.id)
    or (legacy.canonical_key='VIEWER' and target.role_kind='custom'
        and target.name='Legacy Viewer (read-only)')
  );

update platform.workspace_memberships membership
set role_id=history.mapped_role_id
from platform.workspace_role_assignment_history history
where history.workspace_id=membership.workspace_id
  and history.user_id=membership.user_id
  and history.legacy_role_id=membership.role_id;

create table platform.invitation_role_migration_history (
  invitation_id uuid primary key references platform.invitations(id),
  workspace_id uuid not null references platform.workspaces(id),
  legacy_role_id uuid not null references platform.roles(id),
  legacy_role_name text not null,
  mapped_role_id uuid not null references platform.roles(id),
  mapped_role_name text not null,
  recorded_at timestamptz not null default now()
);

insert into platform.invitation_role_migration_history(
  invitation_id,workspace_id,legacy_role_id,legacy_role_name,mapped_role_id,mapped_role_name
)
select invitation.id,invitation.workspace_id,legacy.id,legacy.name,target.id,target.name
from platform.invitations invitation
join platform.roles legacy on legacy.id=invitation.role_id
  and (
    legacy.role_kind='legacy'
    or (legacy.role_kind='built_in' and legacy.canonical_key='MEMBER')
  )
join platform.roles target on target.workspace_id=invitation.workspace_id
  and target.status='active'
  and (
    (legacy.canonical_key in ('OWNER','ADMIN')
      and target.canonical_key='WORKSPACE_MANAGER')
    or (legacy.canonical_key='MEMBER' and target.id=legacy.id)
    or (legacy.canonical_key='VIEWER' and target.role_kind='custom'
        and target.name='Legacy Viewer (read-only)')
  );

update platform.invitations invitation
set role_id=history.mapped_role_id
from platform.invitation_role_migration_history history
where history.invitation_id=invitation.id
  and history.legacy_role_id=invitation.role_id;

create unique index roles_workspace_active_canonical_unique
  on platform.roles(workspace_id,canonical_key)
  where status='active' and canonical_key is not null;

-- ---------------------------------------------------------------------------
-- Independent SYSTEM authority. It is neither a Workspace membership nor an
-- alias for a legacy tenant role.
-- ---------------------------------------------------------------------------
create table platform.system_roles (
  id uuid primary key,
  name text not null,
  role_kind text not null check (role_kind in ('built_in','custom')),
  is_builtin boolean not null,
  status text not null default 'active' check (status in ('active','deprecated')),
  created_at timestamptz not null default now(),
  constraint system_roles_name_nonblank check (btrim(name)<>''),
  constraint system_roles_kind_consistent check (
    (role_kind='built_in' and is_builtin) or (role_kind='custom' and not is_builtin)
  )
);
create unique index system_roles_name_unique on platform.system_roles(lower(name));

create table platform.system_role_permissions (
  role_id uuid not null references platform.system_roles(id) on delete cascade,
  permission_key text not null references platform.permissions(key),
  primary key(role_id,permission_key)
);

create table platform.system_access_assignments (
  user_id uuid not null references auth.users(id),
  role_id uuid not null references platform.system_roles(id),
  status text not null default 'active' check (status in ('active','revoked')),
  assigned_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  primary key(user_id,role_id),
  constraint system_access_disposition_consistent check (
    (status='active' and revoked_at is null)
    or (status='revoked' and revoked_at is not null)
  )
);
create index system_access_assignments_active_user_idx
  on platform.system_access_assignments(user_id) where status='active';

insert into platform.system_roles(id,name,role_kind,is_builtin,status)
values(gen_random_uuid(),'SYSTEM_ADMIN','built_in',true,'active');

insert into platform.system_role_permissions(role_id,permission_key)
select role.id,permission.key
from platform.system_roles role
join platform.permissions permission
  on permission.scope='SYSTEM' and permission.is_active
where role.name='SYSTEM_ADMIN';

-- Project-Control approved initial bootstrap: exactly one existing active
-- profile is required. Identity is not derived from OWNER/ADMIN and no
-- sensitive identifier is embedded in this artifact.
do $$
declare approved_user uuid;
declare candidate_count bigint;
declare administrator_role uuid;
begin
  select count(*) into candidate_count
  from platform.user_profiles where status='active';
  if candidate_count<>1 then
    raise exception using errcode='P0001',
      message='STAGE1_SYSTEM_ADMIN_BOOTSTRAP_REQUIRES_ONE_ACTIVE_PROFILE';
  end if;
  select user_id into strict approved_user
  from platform.user_profiles where status='active';
  select id into strict administrator_role
  from platform.system_roles
  where name='SYSTEM_ADMIN' and role_kind='built_in' and status='active';
  insert into platform.system_access_assignments(
    user_id,role_id,status,assigned_by
  ) values(approved_user,administrator_role,'active',approved_user);
end $$;

-- ---------------------------------------------------------------------------
-- Scope-aware authorization primitives and protected System-access mutation.
-- ---------------------------------------------------------------------------
create or replace function platform.user_has_permission(
  target_workspace_id uuid,required_permission text
) returns boolean language sql stable security definer set search_path='' as $$
  select exists(
    select 1
    from platform.workspace_memberships membership
    join platform.roles role
      on role.id=membership.role_id and role.workspace_id=membership.workspace_id
    join platform.role_permissions assignment on assignment.role_id=role.id
    join platform.permissions permission on permission.key=assignment.permission_key
    where membership.workspace_id=target_workspace_id
      and membership.user_id=platform.current_user_id()
      and membership.status='active'
      and role.status='active'
      and permission.scope='WORKSPACE'
      and permission.is_active
      and permission.key=required_permission
  )
$$;

create function platform.user_has_any_system_access()
returns boolean language sql stable security definer set search_path='' as $$
  select exists(
    select 1 from platform.system_access_assignments assignment
    join platform.system_roles role on role.id=assignment.role_id
    where assignment.user_id=platform.current_user_id()
      and assignment.status='active' and role.status='active'
  )
$$;

create function platform.user_has_system_permission(required_permission text)
returns boolean language sql stable security definer set search_path='' as $$
  select exists(
    select 1 from platform.system_access_assignments assignment
    join platform.system_roles role on role.id=assignment.role_id
    join platform.system_role_permissions role_permission
      on role_permission.role_id=role.id
    join platform.permissions permission
      on permission.key=role_permission.permission_key
    where assignment.user_id=platform.current_user_id()
      and assignment.status='active' and role.status='active'
      and permission.scope='SYSTEM' and permission.is_active
      and permission.key=required_permission
  )
$$;

create function platform.assign_system_access(target_user uuid,target_role uuid)
returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('system_access.manage') then
    return false;
  end if;
  if not exists(select 1 from platform.user_profiles
      where user_id=target_user and status='active')
     or not exists(select 1 from platform.system_roles
      where id=target_role and status='active') then
    return false;
  end if;
  insert into platform.system_access_assignments(
    user_id,role_id,status,assigned_by,revoked_at
  ) values(
    target_user,target_role,'active',platform.current_user_id(),null
  ) on conflict(user_id,role_id) do update set
    status='active',assigned_by=excluded.assigned_by,revoked_at=null;
  return true;
end $$;

create function platform.revoke_system_access(target_user uuid,target_role uuid)
returns boolean language plpgsql security definer set search_path='' as $$
declare is_administrator boolean;
declare active_administrators bigint;
begin
  if not platform.user_has_system_permission('system_access.manage') then
    return false;
  end if;
  perform 1 from platform.system_access_assignments
    where status='active' for update;
  select role.name='SYSTEM_ADMIN' and role.role_kind='built_in'
    into is_administrator
  from platform.system_roles role where role.id=target_role;
  if coalesce(is_administrator,false) then
    select count(*) into active_administrators
    from platform.system_access_assignments assignment
    join platform.system_roles role on role.id=assignment.role_id
    where assignment.status='active' and role.status='active'
      and role.name='SYSTEM_ADMIN' and role.role_kind='built_in';
    if active_administrators<=1 then
      raise exception using errcode='P0001',message='LAST_SYSTEM_ADMIN_REQUIRED';
    end if;
  end if;
  update platform.system_access_assignments
  set status='revoked',revoked_at=now()
  where user_id=target_user and role_id=target_role and status='active';
  return found;
end $$;

create function platform.protect_workspace_role_identity()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
  if old.role_kind<>'custom' then
    raise exception using errcode='P0001',message='BUILT_IN_OR_LEGACY_ROLE_IMMUTABLE';
  end if;
  if tg_op='UPDATE' and (
    new.workspace_id is distinct from old.workspace_id
    or new.role_kind is distinct from old.role_kind
    or new.canonical_key is distinct from old.canonical_key
    or new.is_system is distinct from old.is_system
  ) then
    raise exception using errcode='P0001',message='CUSTOM_ROLE_SCOPE_IMMUTABLE';
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;

create trigger protect_workspace_role_identity_before_change
before update or delete on platform.roles for each row
execute function platform.protect_workspace_role_identity();

create function platform.protect_workspace_role_permissions()
returns trigger language plpgsql security invoker set search_path='' as $$
declare selected_role uuid;
declare selected_permission text;
declare kind text;
declare permission_scope text;
begin
  selected_role:=case when tg_op='DELETE' then old.role_id else new.role_id end;
  selected_permission:=case when tg_op='DELETE' then old.permission_key else new.permission_key end;
  select role_kind into kind from platform.roles where id=selected_role;
  if kind<>'custom' then
    if tg_op='INSERT' and kind='built_in' and current_user<>session_user then
      select scope into permission_scope from platform.permissions
        where key=selected_permission and is_active;
      if permission_scope='WORKSPACE' then return new; end if;
    end if;
    raise exception using errcode='P0001',message='BUILT_IN_ROLE_PERMISSIONS_IMMUTABLE';
  end if;
  if tg_op<>'DELETE' then
    select scope into permission_scope from platform.permissions
      where key=selected_permission and is_active and is_delegable;
    if permission_scope is distinct from 'WORKSPACE' then
      raise exception using errcode='P0001',message='WORKSPACE_ROLE_SCOPE_MISMATCH';
    end if;
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;

create trigger protect_workspace_role_permissions_before_change
before insert or update or delete on platform.role_permissions for each row
execute function platform.protect_workspace_role_permissions();

create function platform.protect_system_role_identity()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
  if old.role_kind<>'custom' or old.is_builtin then
    raise exception using errcode='P0001',message='SYSTEM_BUILT_IN_ROLE_IMMUTABLE';
  end if;
  if tg_op='UPDATE' and (
    new.role_kind is distinct from old.role_kind
    or new.is_builtin is distinct from old.is_builtin
  ) then
    raise exception using errcode='P0001',message='SYSTEM_CUSTOM_ROLE_SCOPE_IMMUTABLE';
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;

create trigger protect_system_role_identity_before_change
before update or delete on platform.system_roles for each row
execute function platform.protect_system_role_identity();

create function platform.protect_system_role_permissions()
returns trigger language plpgsql security invoker set search_path='' as $$
declare selected_role uuid;
declare selected_permission text;
declare kind text;
declare permission_scope text;
begin
  selected_role:=case when tg_op='DELETE' then old.role_id else new.role_id end;
  selected_permission:=case when tg_op='DELETE' then old.permission_key else new.permission_key end;
  select role_kind into kind from platform.system_roles where id=selected_role;
  if kind<>'custom' then
    raise exception using errcode='P0001',message='SYSTEM_BUILT_IN_PERMISSIONS_IMMUTABLE';
  end if;
  if tg_op<>'DELETE' then
    select scope into permission_scope from platform.permissions
      where key=selected_permission and is_active and is_delegable;
    if permission_scope is distinct from 'SYSTEM' then
      raise exception using errcode='P0001',message='SYSTEM_ROLE_SCOPE_MISMATCH';
    end if;
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;

create trigger protect_system_role_permissions_before_change
before insert or update or delete on platform.system_role_permissions for each row
execute function platform.protect_system_role_permissions();

-- Final membership primitives are System-authorized. No Workspace role,
-- including WORKSPACE_MANAGER, can mutate memberships or invitations.
create or replace function platform.change_membership_role(
  target_workspace uuid,target_user uuid,new_role uuid
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('members.manage') then return false; end if;
  if not exists(
    select 1 from platform.roles role
    where role.id=new_role and role.workspace_id=target_workspace
      and role.status='active' and role.role_kind in ('built_in','custom')
  ) then return false; end if;
  update platform.workspace_memberships
  set role_id=new_role
  where workspace_id=target_workspace and user_id=target_user;
  return found;
end $$;

create or replace function platform.remove_workspace_member(
  target_workspace uuid,target_user uuid
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('members.manage') then return false; end if;
  delete from platform.workspace_memberships
  where workspace_id=target_workspace and user_id=target_user;
  return found;
end $$;

create or replace function platform.revoke_invitation(
  target_workspace uuid,target_invitation uuid
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('invitations.manage') then return false; end if;
  update platform.invitations set status='revoked'
  where id=target_invitation and workspace_id=target_workspace and status='pending';
  return found;
end $$;

create function platform.create_workspace_stage1(
  new_workspace_id uuid,new_workspace_name text
) returns void language plpgsql security definer set search_path='' as $$
declare created_role_id uuid;
begin
  if not platform.user_has_system_permission('workspace.manage') then
    raise exception using errcode='P0001',message='SYSTEM_WORKSPACE_MANAGE_REQUIRED';
  end if;
  if btrim(new_workspace_name)='' then
    raise exception using errcode='22023',message='WORKSPACE_NAME_REQUIRED';
  end if;
  insert into platform.workspaces(id,name) values(new_workspace_id,new_workspace_name);
  insert into platform.roles(
    id,workspace_id,name,is_system,role_kind,status,canonical_key
  ) values(
    gen_random_uuid(),new_workspace_id,'WORKSPACE_MANAGER',true,
    'built_in','active','WORKSPACE_MANAGER'
  ) returning id into created_role_id;
  insert into platform.role_permissions(role_id,permission_key)
  select created_role_id,key from platform.permissions
  where scope='WORKSPACE' and is_active;
  insert into platform.roles(
    id,workspace_id,name,is_system,role_kind,status,canonical_key
  ) values(
    gen_random_uuid(),new_workspace_id,'MEMBER',true,
    'built_in','active','MEMBER'
  ) returning id into created_role_id;
  insert into platform.role_permissions(role_id,permission_key)
  select created_role_id,key from platform.permissions where key in (
    'workspace.read','assistant.read','knowledge.read',
    'conversations.read','conversations.create','conversations.rename',
    'conversations.archive','members.read','notifications.read'
  );
  insert into platform.roles(
    id,workspace_id,name,is_system,role_kind,status,canonical_key
  ) values(
    gen_random_uuid(),new_workspace_id,'Legacy Viewer (read-only)',false,
    'custom','active',null
  ) returning id into created_role_id;
  insert into platform.role_permissions(role_id,permission_key)
  select created_role_id,key from platform.permissions where key in (
    'workspace.read','assistant.read','knowledge.read','conversations.read',
    'evaluation.read','members.read','notifications.read'
  );
end $$;

-- ---------------------------------------------------------------------------
-- Workspace operational state and final operational policies.
-- SUSPENDED always disables AI; disabling AI does not suspend a Workspace.
-- ---------------------------------------------------------------------------
alter table platform.workspaces
  add column operational_status text not null default 'ACTIVE',
  add column ai_execution_enabled boolean not null default true,
  add constraint workspaces_operational_status_vocabulary
    check(operational_status in ('ACTIVE','SUSPENDED')),
  add constraint workspaces_suspended_disables_ai
    check(operational_status<>'SUSPENDED' or not ai_execution_enabled);

alter table platform.governance_settings add column is_active boolean not null default true;
alter table platform.governance_settings
  drop constraint if exists governance_settings_setting_key_check;
alter table platform.governance_settings
  add constraint governance_settings_setting_key_final check(setting_key in (
    'assistant_creation_enabled','knowledge_source_addition_enabled',
    'knowledge_processing_enabled'
  ));
update platform.governance_settings
set is_active=false where setting_key='assistant_creation_enabled';
insert into platform.governance_settings(workspace_id,setting_key,enabled,is_active)
select workspace.id,policy.key,true,true
from platform.workspaces workspace
cross join(values('knowledge_source_addition_enabled'),('knowledge_processing_enabled')) policy(key)
on conflict(workspace_id,setting_key) do update set is_active=true;

create or replace function platform.stage7b_seed_governance()
returns trigger language plpgsql security definer set search_path='' as $$
begin
  insert into platform.governance_settings(
    workspace_id,setting_key,enabled,is_active
  ) values
    (new.id,'knowledge_source_addition_enabled',true,true),
    (new.id,'knowledge_processing_enabled',true,true);
  return new;
end $$;

-- Retain historical entitlement rows but remove Assistant quota enforcement.
drop trigger if exists stage7c_assistant_limit_before_insert on platform.assistants;

create function platform.update_workspace_operational_state(
  target_workspace uuid,new_status text,new_ai_execution_enabled boolean
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('governance.manage') then
    return false;
  end if;
  if new_status not in ('ACTIVE','SUSPENDED') then
    raise exception using errcode='22023',message='WORKSPACE_STATUS_INVALID';
  end if;
  update platform.workspaces
  set operational_status=new_status,
      ai_execution_enabled=case
        when new_status='SUSPENDED' then false else new_ai_execution_enabled end
  where id=target_workspace;
  return found;
end $$;

-- ---------------------------------------------------------------------------
-- Workspace Conversation lifecycle. Existing IDs/messages/evidence remain;
-- missing historical titles receive a deterministic identifier-derived value.
-- ---------------------------------------------------------------------------
alter table platform.conversations
  add column title text,
  add column status text not null default 'ACTIVE',
  add column updated_at timestamptz,
  add column archived_at timestamptz;
update platform.conversations
set title='Conversation '||substr(id::text,1,8),
    updated_at=created_at
where title is null;
alter table platform.conversations
  alter column title set not null,
  alter column title set default 'Untitled conversation',
  add constraint conversations_title_nonblank check(btrim(title)<>''),
  add constraint conversations_status_vocabulary check(status in ('ACTIVE','ARCHIVED')),
  add constraint conversations_archive_state_consistent check(
    (status='ACTIVE' and archived_at is null)
    or (status='ARCHIVED' and archived_at is not null)
  );
create index conversations_workspace_status_updated_idx
  on platform.conversations(workspace_id,status,updated_at desc,id);

create unique index assistants_id_workspace_unique
  on platform.assistants(id,workspace_id);
alter table platform.conversations
  add constraint conversations_assistant_workspace_fk
  foreign key(assistant_id,workspace_id)
  references platform.assistants(id,workspace_id);

create function platform.rename_workspace_conversation(
  target_workspace uuid,target_conversation uuid,new_title text
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if target_workspace is distinct from
      nullif(current_setting('app.workspace_id',true),'')::uuid
     or not platform.user_has_permission(target_workspace,'conversations.rename') then
    return false;
  end if;
  if btrim(new_title)='' or char_length(btrim(new_title))>200 then
    raise exception using errcode='22023',message='CONVERSATION_TITLE_INVALID';
  end if;
  update platform.conversations set title=btrim(new_title),updated_at=now()
  where id=target_conversation and workspace_id=target_workspace;
  return found;
end $$;

create function platform.set_workspace_conversation_archived(
  target_workspace uuid,target_conversation uuid,new_archived boolean
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if target_workspace is distinct from
      nullif(current_setting('app.workspace_id',true),'')::uuid
     or not platform.user_has_permission(target_workspace,'conversations.archive') then
    return false;
  end if;
  update platform.conversations
  set status=case when new_archived then 'ARCHIVED' else 'ACTIVE' end,
      archived_at=case when new_archived then coalesce(archived_at,now()) else null end,
      updated_at=now()
  where id=target_conversation and workspace_id=target_workspace;
  return found;
end $$;

-- ---------------------------------------------------------------------------
-- Distinct SYSTEM Conversation aggregate. created_by is provenance only and
-- deliberately absent from every visibility predicate.
-- ---------------------------------------------------------------------------
create table platform.system_conversations(
  id uuid primary key,
  title text not null,
  status text not null default 'ACTIVE',
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz,
  constraint system_conversations_title_nonblank check(btrim(title)<>''),
  constraint system_conversations_status_vocabulary check(status in ('ACTIVE','ARCHIVED')),
  constraint system_conversations_archive_state_consistent check(
    (status='ACTIVE' and archived_at is null)
    or (status='ARCHIVED' and archived_at is not null)
  )
);
create index system_conversations_status_updated_idx
  on platform.system_conversations(status,updated_at desc,id);

create table platform.system_conversation_messages(
  conversation_id uuid not null references platform.system_conversations(id),
  sequence integer not null,
  role text not null,
  content text not null,
  created_at timestamptz not null default now(),
  primary key(conversation_id,sequence),
  constraint system_conversation_messages_sequence_nonnegative check(sequence>=0),
  constraint system_conversation_messages_role_vocabulary check(role in ('user','assistant')),
  constraint system_conversation_messages_content_nonblank check(btrim(content)<>'')
);

create function platform.rename_system_conversation(
  target_conversation uuid,new_title text
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('system_conversations.rename') then
    return false;
  end if;
  if btrim(new_title)='' or char_length(btrim(new_title))>200 then
    raise exception using errcode='22023',message='SYSTEM_CONVERSATION_TITLE_INVALID';
  end if;
  update platform.system_conversations
  set title=btrim(new_title),updated_at=now()
  where id=target_conversation;
  return found;
end $$;

create function platform.set_system_conversation_archived(
  target_conversation uuid,new_archived boolean
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('system_conversations.archive') then
    return false;
  end if;
  update platform.system_conversations
  set status=case when new_archived then 'ARCHIVED' else 'ACTIVE' end,
      archived_at=case when new_archived then coalesce(archived_at,now()) else null end,
      updated_at=now()
  where id=target_conversation;
  return found;
end $$;

-- ---------------------------------------------------------------------------
-- Evaluation persistence reconciliation. Existing workspace/suite identity
-- and results are preserved; historically unknown actor/Assistant stays NULL.
-- ---------------------------------------------------------------------------
alter table evaluation.evaluation_runs
  add column assistant_id uuid,
  add column requested_by uuid references auth.users(id) on delete set null,
  add column created_at timestamptz,
  add column started_at timestamptz,
  add column completed_at timestamptz,
  add column failure_category text;
alter table evaluation.evaluation_runs
  add constraint evaluation_runs_assistant_workspace_fk
  foreign key(assistant_id,workspace_id)
  references platform.assistants(id,workspace_id);
create index evaluation_runs_workspace_started_idx
  on evaluation.evaluation_runs(workspace_id,started_at desc,id);
create index evaluation_runs_workspace_assistant_started_idx
  on evaluation.evaluation_runs(workspace_id,assistant_id,started_at desc)
  where assistant_id is not null;

-- ---------------------------------------------------------------------------
-- RLS: SYSTEM and WORKSPACE scopes are independent. An arbitrary Workspace
-- GUC is never sufficient and System access never implies tenant conversation
-- access.
-- ---------------------------------------------------------------------------
alter table platform.workspace_role_assignment_history enable row level security;
alter table platform.workspace_role_assignment_history force row level security;
alter table platform.invitation_role_migration_history enable row level security;
alter table platform.invitation_role_migration_history force row level security;
alter table platform.system_roles enable row level security;
alter table platform.system_roles force row level security;
alter table platform.system_role_permissions enable row level security;
alter table platform.system_role_permissions force row level security;
alter table platform.system_access_assignments enable row level security;
alter table platform.system_access_assignments force row level security;
alter table platform.system_conversations enable row level security;
alter table platform.system_conversations force row level security;
alter table platform.system_conversation_messages enable row level security;
alter table platform.system_conversation_messages force row level security;

drop policy if exists user_profiles_runtime_select on platform.user_profiles;
create policy user_profiles_runtime_select on platform.user_profiles
for select to knowledge_platform_runtime using(
  user_id=platform.current_user_id()
  or platform.user_has_system_permission('system_memberships.read')
  or exists(
    select 1 from platform.workspace_memberships membership
    where membership.user_id=user_profiles.user_id
      and membership.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
      and platform.user_has_permission(membership.workspace_id,'members.read')
  )
);

drop policy if exists memberships_runtime_select on platform.workspace_memberships;
create policy memberships_runtime_select on platform.workspace_memberships
for select to knowledge_platform_runtime using(
  user_id=platform.current_user_id()
  or platform.user_has_system_permission('system_memberships.read')
  or (
    workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and platform.user_has_permission(workspace_id,'members.read')
  )
);

drop policy if exists roles_runtime_select on platform.roles;
drop policy if exists roles_runtime_insert on platform.roles;
drop policy if exists roles_runtime_update on platform.roles;
drop policy if exists roles_runtime_delete on platform.roles;
create policy roles_runtime_select on platform.roles
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_system_permission('roles.read')
    or platform.user_has_permission(workspace_id,'members.read')
    or exists(
      select 1 from platform.workspace_memberships membership
      where membership.workspace_id=roles.workspace_id
        and membership.user_id=platform.current_user_id()
        and membership.role_id=roles.id and membership.status='active'
    )
  )
);
create policy roles_runtime_insert on platform.roles
for insert to knowledge_platform_runtime with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and status='active' and not is_system
);
create policy roles_runtime_update on platform.roles
for update to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and status='active' and not is_system
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and status='active' and not is_system
);
create policy roles_runtime_delete on platform.roles
for delete to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and status='active' and not is_system
);

drop policy if exists role_permissions_runtime_select on platform.role_permissions;
drop policy if exists role_permissions_runtime_manage on platform.role_permissions;
create policy role_permissions_runtime_select on platform.role_permissions
for select to knowledge_platform_runtime using(exists(
  select 1 from platform.roles role
  where role.id=role_permissions.role_id
    and role.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and (
      platform.user_has_system_permission('roles.read')
      or exists(
        select 1 from platform.workspace_memberships membership
        where membership.workspace_id=role.workspace_id
          and membership.user_id=platform.current_user_id()
          and membership.role_id=role.id and membership.status='active'
      )
    )
));
create policy role_permissions_runtime_manage on platform.role_permissions
for all to knowledge_platform_runtime using(exists(
  select 1 from platform.roles role
  where role.id=role_permissions.role_id
    and role.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and role.role_kind='custom' and role.status='active'
    and platform.user_has_system_permission('roles.manage')
)) with check(exists(
  select 1 from platform.roles role
  join platform.permissions permission
    on permission.key=role_permissions.permission_key
  where role.id=role_permissions.role_id
    and role.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and role.role_kind='custom' and role.status='active'
    and permission.scope='WORKSPACE' and permission.is_active
    and permission.is_delegable
    and platform.user_has_system_permission('roles.manage')
));

drop policy if exists teams_runtime_select on platform.teams;
drop policy if exists teams_runtime_manage on platform.teams;
create policy teams_runtime_select on platform.teams
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('teams.read')
);
create policy teams_runtime_manage on platform.teams
for all to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('teams.manage')
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('teams.manage')
);

drop policy if exists team_members_runtime_select on platform.team_members;
drop policy if exists team_members_runtime_manage on platform.team_members;
create policy team_members_runtime_select on platform.team_members
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('teams.read')
);
create policy team_members_runtime_manage on platform.team_members
for all to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('teams.manage')
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('teams.manage')
);

drop policy if exists invitations_runtime_select on platform.invitations;
drop policy if exists invitations_runtime_insert on platform.invitations;
create policy invitations_runtime_select on platform.invitations
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('invitations.read')
);
create policy invitations_runtime_insert on platform.invitations
for insert to knowledge_platform_runtime with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and invited_by=platform.current_user_id()
  and platform.user_has_system_permission('invitations.manage')
  and exists(
    select 1 from platform.roles role
    where role.id=invitations.role_id and role.workspace_id=invitations.workspace_id
      and role.status='active' and role.role_kind in ('built_in','custom')
  )
);

create policy workspace_role_history_runtime_select
on platform.workspace_role_assignment_history for select to knowledge_platform_runtime
using(platform.user_has_system_permission('system_access.read'));
create policy invitation_role_history_runtime_select
on platform.invitation_role_migration_history for select to knowledge_platform_runtime
using(platform.user_has_system_permission('system_access.read'));

create policy system_roles_runtime_select on platform.system_roles
for select to knowledge_platform_runtime using(
  platform.user_has_system_permission('roles.read')
  or exists(
    select 1 from platform.system_access_assignments assignment
    where assignment.role_id=system_roles.id
      and assignment.user_id=platform.current_user_id()
      and assignment.status='active'
  )
);
create policy system_roles_runtime_insert on platform.system_roles
for insert to knowledge_platform_runtime with check(
  platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and not is_builtin and status='active'
);
create policy system_roles_runtime_update on platform.system_roles
for update to knowledge_platform_runtime using(
  platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and not is_builtin
) with check(
  platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and not is_builtin
);
create policy system_roles_runtime_delete on platform.system_roles
for delete to knowledge_platform_runtime using(
  platform.user_has_system_permission('roles.manage')
  and role_kind='custom' and not is_builtin
);
create policy system_role_permissions_runtime_select
on platform.system_role_permissions for select to knowledge_platform_runtime
using(
  platform.user_has_system_permission('roles.read')
  or exists(
    select 1 from platform.system_access_assignments assignment
    where assignment.role_id=system_role_permissions.role_id
      and assignment.user_id=platform.current_user_id()
      and assignment.status='active'
  )
);
create policy system_role_permissions_runtime_manage
on platform.system_role_permissions for all to knowledge_platform_runtime
using(exists(
  select 1 from platform.system_roles role
  where role.id=system_role_permissions.role_id and role.role_kind='custom'
    and not role.is_builtin and platform.user_has_system_permission('roles.manage')
)) with check(exists(
  select 1 from platform.system_roles role
  join platform.permissions permission
    on permission.key=system_role_permissions.permission_key
  where role.id=system_role_permissions.role_id and role.role_kind='custom'
    and not role.is_builtin and permission.scope='SYSTEM'
    and permission.is_active and permission.is_delegable
    and platform.user_has_system_permission('roles.manage')
));
create policy system_access_assignments_runtime_select
on platform.system_access_assignments for select to knowledge_platform_runtime
using(
  user_id=platform.current_user_id()
  or platform.user_has_system_permission('system_access.read')
);

drop policy if exists workspaces_runtime_select on platform.workspaces;
drop policy if exists workspaces_runtime_insert on platform.workspaces;
drop policy if exists workspaces_runtime_update on platform.workspaces;
drop policy if exists workspaces_runtime_delete on platform.workspaces;
create policy workspaces_runtime_select on platform.workspaces
for select to knowledge_platform_runtime using(
  platform.user_has_workspace_membership(id)
  or platform.user_has_system_permission('system_workspaces.read')
  or platform.user_has_system_permission('workspace.manage')
);
create policy workspaces_runtime_insert on platform.workspaces
for insert to knowledge_platform_runtime with check(false);
create policy workspaces_runtime_update on platform.workspaces
for update to knowledge_platform_runtime using(false) with check(false);
create policy workspaces_runtime_delete on platform.workspaces
for delete to knowledge_platform_runtime using(false);

drop policy if exists assistants_runtime_select on platform.assistants;
drop policy if exists assistants_runtime_insert on platform.assistants;
drop policy if exists assistants_runtime_update on platform.assistants;
drop policy if exists assistants_runtime_delete on platform.assistants;
create policy assistants_runtime_select on platform.assistants
for select to knowledge_platform_runtime using(
  (workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and platform.user_has_permission(workspace_id,'assistant.read'))
  or platform.user_has_system_permission('system_assistants.read')
);
create policy assistants_runtime_insert on platform.assistants
for insert to knowledge_platform_runtime with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('assistant.create')
);
create policy assistants_runtime_update on platform.assistants
for update to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('assistant.update')
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('assistant.update')
);
create policy assistants_runtime_delete on platform.assistants
for delete to knowledge_platform_runtime using(false);

drop policy if exists knowledge_sources_runtime_select on platform.knowledge_sources;
drop policy if exists knowledge_sources_runtime_insert on platform.knowledge_sources;
drop policy if exists knowledge_sources_runtime_update on platform.knowledge_sources;
drop policy if exists knowledge_sources_runtime_delete on platform.knowledge_sources;
create policy knowledge_sources_runtime_select on platform.knowledge_sources
for select to knowledge_platform_runtime using(
  (workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and platform.user_has_permission(workspace_id,'knowledge.read'))
  or platform.user_has_system_permission('system_knowledge.read')
);
create policy knowledge_sources_runtime_insert on platform.knowledge_sources
for insert to knowledge_platform_runtime with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'knowledge.create')
    or platform.user_has_system_permission('system_knowledge.create')
  )
);
create policy knowledge_sources_runtime_update on platform.knowledge_sources
for update to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'knowledge.process')
    or platform.user_has_system_permission('system_knowledge.process')
  )
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'knowledge.process')
    or platform.user_has_system_permission('system_knowledge.process')
  )
);
create policy knowledge_sources_runtime_delete on platform.knowledge_sources
for delete to knowledge_platform_runtime using(false);

drop policy if exists assistant_knowledge_sources_runtime_select
  on platform.assistant_knowledge_sources;
drop policy if exists assistant_knowledge_sources_runtime_insert
  on platform.assistant_knowledge_sources;
drop policy if exists assistant_knowledge_sources_runtime_delete
  on platform.assistant_knowledge_sources;
create policy assistant_knowledge_sources_runtime_select
on platform.assistant_knowledge_sources for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'knowledge.read')
    or platform.user_has_system_permission('system_knowledge.read')
  )
);
create policy assistant_knowledge_sources_runtime_insert
on platform.assistant_knowledge_sources for insert to knowledge_platform_runtime
with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('knowledge.attach')
  and exists(select 1 from platform.assistants assistant
    where assistant.id=assistant_knowledge_sources.assistant_id
      and assistant.workspace_id=assistant_knowledge_sources.workspace_id)
  and exists(select 1 from platform.knowledge_sources source
    where source.id=assistant_knowledge_sources.knowledge_source_id
      and source.workspace_id=assistant_knowledge_sources.workspace_id)
);
create policy assistant_knowledge_sources_runtime_delete
on platform.assistant_knowledge_sources for delete to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('knowledge.attach')
);

drop policy if exists conversations_runtime_select on platform.conversations;
drop policy if exists conversations_runtime_insert on platform.conversations;
create policy conversations_runtime_select on platform.conversations
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_permission(workspace_id,'conversations.read')
);
create policy conversations_runtime_insert on platform.conversations
for insert to knowledge_platform_runtime with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_permission(workspace_id,'conversations.create')
  and exists(select 1 from platform.assistants assistant
    where assistant.id=conversations.assistant_id
      and assistant.workspace_id=conversations.workspace_id)
);

drop policy if exists messages_runtime_select on platform.messages;
drop policy if exists messages_runtime_insert on platform.messages;
create policy messages_runtime_select on platform.messages
for select to knowledge_platform_runtime using(exists(
  select 1 from platform.conversations conversation
  where conversation.id=messages.conversation_id
    and conversation.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and platform.user_has_permission(conversation.workspace_id,'conversations.read')
));
create policy messages_runtime_insert on platform.messages
for insert to knowledge_platform_runtime with check(exists(
  select 1 from platform.conversations conversation
  where conversation.id=messages.conversation_id
    and conversation.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and conversation.status='ACTIVE'
    and platform.user_has_permission(conversation.workspace_id,'conversations.create')
));

drop policy if exists message_evidence_runtime_select on platform.message_evidence;
drop policy if exists message_evidence_runtime_insert on platform.message_evidence;
create policy message_evidence_runtime_select on platform.message_evidence
for select to knowledge_platform_runtime using(exists(
  select 1 from platform.conversations conversation
  where conversation.id=message_evidence.conversation_id
    and conversation.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and platform.user_has_permission(conversation.workspace_id,'conversations.read')
));
create policy message_evidence_runtime_insert on platform.message_evidence
for insert to knowledge_platform_runtime with check(exists(
  select 1 from platform.conversations conversation
  join platform.knowledge_sources source
    on source.id=message_evidence.source_id
   and source.workspace_id=conversation.workspace_id
  where conversation.id=message_evidence.conversation_id
    and conversation.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and conversation.status='ACTIVE'
    and platform.user_has_permission(conversation.workspace_id,'conversations.create')
));

create policy system_conversations_runtime_select
on platform.system_conversations for select to knowledge_platform_runtime
using(platform.user_has_system_permission('system_conversations.read'));
create policy system_conversations_runtime_insert
on platform.system_conversations for insert to knowledge_platform_runtime
with check(
  platform.user_has_system_permission('system_conversations.create')
  and created_by=platform.current_user_id()
);
create policy system_conversations_runtime_update
on platform.system_conversations for update to knowledge_platform_runtime
using(false) with check(false);
create policy system_conversations_runtime_delete
on platform.system_conversations for delete to knowledge_platform_runtime using(false);
create policy system_conversation_messages_runtime_select
on platform.system_conversation_messages for select to knowledge_platform_runtime
using(
  platform.user_has_system_permission('system_conversations.read')
  and exists(select 1 from platform.system_conversations conversation
    where conversation.id=system_conversation_messages.conversation_id)
);
create policy system_conversation_messages_runtime_insert
on platform.system_conversation_messages for insert to knowledge_platform_runtime
with check(
  platform.user_has_system_permission('system_conversations.create')
  and exists(select 1 from platform.system_conversations conversation
    where conversation.id=system_conversation_messages.conversation_id
      and conversation.status='ACTIVE')
);

drop policy if exists evaluation_runs_workspace on evaluation.evaluation_runs;
drop policy if exists evaluation_results_workspace on evaluation.evaluation_results;
create policy evaluation_runs_runtime_select on evaluation.evaluation_runs
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'evaluation.read')
    or (
      requested_by=platform.current_user_id()
      and platform.user_has_permission(workspace_id,'evaluation.run')
    )
  )
);
create policy evaluation_runs_runtime_insert on evaluation.evaluation_runs
for insert to knowledge_platform_runtime with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and requested_by=platform.current_user_id()
  and platform.user_has_permission(workspace_id,'evaluation.run')
  and (assistant_id is null or exists(
    select 1 from platform.assistants assistant
    where assistant.id=evaluation_runs.assistant_id
      and assistant.workspace_id=evaluation_runs.workspace_id))
);
create policy evaluation_runs_runtime_update on evaluation.evaluation_runs
for update to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and requested_by=platform.current_user_id()
  and platform.user_has_permission(workspace_id,'evaluation.run')
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and requested_by=platform.current_user_id()
  and platform.user_has_permission(workspace_id,'evaluation.run')
);
create policy evaluation_results_runtime_select on evaluation.evaluation_results
for select to knowledge_platform_runtime using(exists(
  select 1 from evaluation.evaluation_runs run
  where run.id=evaluation_results.run_id
    and run.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and (
      platform.user_has_permission(run.workspace_id,'evaluation.read')
      or (
        run.requested_by=platform.current_user_id()
        and platform.user_has_permission(run.workspace_id,'evaluation.run')
      )
    )
));
create policy evaluation_results_runtime_insert on evaluation.evaluation_results
for insert to knowledge_platform_runtime with check(exists(
  select 1 from evaluation.evaluation_runs run
  where run.id=evaluation_results.run_id
    and run.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and run.requested_by=platform.current_user_id()
    and platform.user_has_permission(run.workspace_id,'evaluation.run')
));

drop policy if exists representations_workspace on retrieval.document_representations;
drop policy if exists chunks_workspace on retrieval.document_chunks;
create policy representations_workspace on retrieval.document_representations
for all to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'knowledge.read')
    or platform.user_has_system_permission('system_knowledge.read')
  )
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_permission(workspace_id,'knowledge.process')
    or platform.user_has_system_permission('system_knowledge.process')
  )
);
create policy chunks_workspace on retrieval.document_chunks
for all to knowledge_platform_runtime using(exists(
  select 1 from retrieval.document_representations representation
  where representation.id=document_chunks.representation_id
    and representation.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and (
      platform.user_has_permission(representation.workspace_id,'knowledge.read')
      or platform.user_has_system_permission('system_knowledge.read')
    )
)) with check(exists(
  select 1 from retrieval.document_representations representation
  where representation.id=document_chunks.representation_id
    and representation.workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
    and (
      platform.user_has_permission(representation.workspace_id,'knowledge.process')
      or platform.user_has_system_permission('system_knowledge.process')
    )
));

-- Existing append-only observability stays workspace-owned. System actions may
-- append safe records for their explicit target Workspace, but System read
-- permissions do not confer access to Workspace conversations.
create or replace function platform.append_audit_event(
  target_workspace uuid,event_action text,event_resource_type text,
  event_resource_id uuid,event_outcome text,event_request_id text,
  event_metadata jsonb default '{}'::jsonb
) returns uuid language plpgsql security definer set search_path='' as $$
declare event_id uuid;
begin
  if not platform.user_has_workspace_membership(target_workspace)
     and not platform.user_has_any_system_access() then
    raise exception 'audit actor has no applicable authority';
  end if;
  insert into platform.audit_events(
    workspace_id,actor_user_id,action,resource_type,resource_id,
    outcome,request_id,metadata
  ) values(
    target_workspace,platform.current_user_id(),event_action,event_resource_type,
    event_resource_id,event_outcome,nullif(event_request_id,''),
    coalesce(event_metadata,'{}'::jsonb)
  ) returning id into event_id;
  return event_id;
end $$;

create or replace function platform.record_usage_event(
  target_workspace uuid,usage_type text,usage_quantity numeric,
  usage_unit text,usage_resource_type text,usage_resource_id uuid,
  usage_metadata jsonb default '{}'::jsonb
) returns uuid language plpgsql security definer set search_path='' as $$
declare event_id uuid;
begin
  if not platform.user_has_workspace_membership(target_workspace)
     and not platform.user_has_any_system_access() then
    raise exception 'usage actor has no applicable authority';
  end if;
  insert into platform.usage_events(
    workspace_id,actor_user_id,event_type,quantity,unit,
    resource_type,resource_id,metadata
  ) values(
    target_workspace,platform.current_user_id(),usage_type,usage_quantity,
    usage_unit,usage_resource_type,usage_resource_id,
    coalesce(usage_metadata,'{}'::jsonb)
  ) returning id into event_id;
  return event_id;
end $$;

create or replace function platform.record_administrative_operation(
  target_workspace uuid,event_operation_type text,event_status text,
  event_resource_type text,event_resource_id uuid,event_started_at timestamptz,
  event_error_category text
) returns uuid language plpgsql security definer set search_path='' as $$
declare operation_id uuid;
begin
  if not platform.user_has_any_system_access() then
    raise exception 'System authority required';
  end if;
  insert into platform.administrative_operations(
    workspace_id,actor_user_id,operation_type,status,resource_type,
    resource_id,started_at,safe_error_category
  ) values(
    target_workspace,platform.current_user_id(),event_operation_type,
    event_status,event_resource_type,event_resource_id,event_started_at,
    event_error_category
  ) returning id into operation_id;
  return operation_id;
end $$;

create or replace function platform.enqueue_notification(
  target_workspace uuid,target_recipient uuid,event_category text,
  event_severity text,event_title text,event_message text,
  event_resource_type text,event_resource_id uuid
) returns uuid language plpgsql security definer set search_path='' as $$
declare notification_id uuid;
begin
  if not platform.user_has_system_permission('notifications.manage') then
    raise exception 'notification management permission required';
  end if;
  if not exists(
    select 1 from platform.workspace_memberships membership
    where membership.workspace_id=target_workspace
      and membership.user_id=target_recipient and membership.status='active'
  ) then raise exception 'notification recipient is not an active member'; end if;
  insert into platform.notifications(
    workspace_id,recipient_user_id,category,severity,title,message,
    resource_type,resource_id
  ) values(
    target_workspace,target_recipient,event_category,event_severity,event_title,
    event_message,event_resource_type,event_resource_id
  ) returning id into notification_id;
  return notification_id;
end $$;

create or replace function platform.check_workspace_entitlement(
  target_workspace uuid,requested_key text,current_count bigint
) returns text language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_workspace_membership(target_workspace)
     and not platform.user_has_any_system_access() then
    return 'WORKSPACE_AUTHORITY_REQUIRED';
  end if;
  return platform.stage7c_entitlement_decision(
    target_workspace,requested_key,current_count
  );
end $$;

create or replace function platform.resolve_entitlement(
  target_workspace uuid,requested_key text
) returns bigint language plpgsql security definer stable set search_path='' as $$
declare result bigint;
begin
  if not platform.user_has_workspace_membership(target_workspace)
     and not platform.user_has_system_permission('subscriptions.read') then
    raise exception 'workspace or System subscription authority required';
  end if;
  select entitlement.limit_value into result
  from platform.workspace_subscriptions subscription
  join platform.plan_entitlements entitlement
    on entitlement.plan_id=subscription.plan_id
  where subscription.workspace_id=target_workspace
    and entitlement.entitlement_key=requested_key;
  return result;
end $$;

create or replace function platform.check_invitation_creation(
  target_workspace uuid,requested_expiry timestamptz
) returns text language plpgsql security definer set search_path='' as $$
declare settings platform.workspace_security_settings%rowtype;
begin
  if not platform.user_has_system_permission('invitations.manage') then
    return 'SECURITY_POLICY_DENIED';
  end if;
  select * into settings from platform.workspace_security_settings
    where workspace_id=target_workspace;
  if not found or not settings.invitations_enabled then
    return 'SECURITY_POLICY_DENIED';
  end if;
  if requested_expiry>now()+make_interval(days=>settings.max_invitation_expiry_days) then
    return 'INVITATION_EXPIRY_EXCEEDS_POLICY';
  end if;
  return null;
end $$;

create or replace function platform.check_api_key_creation(target_workspace uuid)
returns text language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('api_keys.manage') then
    return 'API_KEY_PERMISSION_DENIED';
  end if;
  if not coalesce((select api_keys_enabled
      from platform.workspace_security_settings
      where workspace_id=target_workspace),false) then
    return 'SECURITY_POLICY_DENIED';
  end if;
  return platform.stage7c_entitlement_decision(target_workspace,'max_api_keys',0);
end $$;

create or replace function platform.revoke_workspace_api_key(
  target_workspace uuid,target_key uuid
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('api_keys.manage') then return false; end if;
  update platform.workspace_api_keys set revoked_at=coalesce(revoked_at,now())
  where id=target_key and workspace_id=target_workspace and revoked_at is null;
  return found;
end $$;

create or replace function platform.update_workspace_provider(
  target_workspace uuid,target_provider text,new_enabled boolean,
  new_status text,new_base_url text
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('providers.manage') then return false; end if;
  update platform.workspace_provider_settings
  set enabled=new_enabled,administrative_status=new_status,
      base_url_override=new_base_url,updated_by=platform.current_user_id(),updated_at=now()
  where workspace_id=target_workspace and provider_code=target_provider;
  return found;
end $$;

create or replace function platform.save_credential_reference(
  target_workspace uuid,reference_name text,target_provider text,
  target_reference text,new_status text
) returns uuid language plpgsql security definer set search_path='' as $$
declare reference_id uuid;
begin
  if not platform.user_has_system_permission('credentials.manage') then
    raise exception using errcode='P0001',message='CREDENTIAL_PERMISSION_DENIED';
  end if;
  insert into platform.credential_references(
    workspace_id,name,provider_code,secret_reference,status,updated_by
  ) values(
    target_workspace,reference_name,target_provider,target_reference,new_status,
    platform.current_user_id()
  ) on conflict(workspace_id,name) do update set
    provider_code=excluded.provider_code,secret_reference=excluded.secret_reference,
    status=excluded.status,updated_by=excluded.updated_by,updated_at=now()
  returning id into reference_id;
  return reference_id;
end $$;

create or replace function platform.delete_credential_reference(
  target_workspace uuid,target_reference uuid
) returns boolean language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('credentials.manage') then return false; end if;
  delete from platform.credential_references
  where workspace_id=target_workspace and id=target_reference;
  return found;
end $$;

create or replace function platform.update_workspace_security(
  target_workspace uuid,keys_enabled boolean,invites_enabled boolean,
  expiry_days integer
) returns void language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('security.manage') then
    raise exception using errcode='P0001',message='SECURITY_PERMISSION_DENIED';
  end if;
  update platform.workspace_security_settings set
    api_keys_enabled=keys_enabled,invitations_enabled=invites_enabled,
    max_invitation_expiry_days=expiry_days,
    updated_by=platform.current_user_id(),updated_at=now()
  where workspace_id=target_workspace;
end $$;

create or replace function platform.update_workspace_settings(
  target_workspace uuid,new_display_name text,new_locale text,
  new_timezone text,new_contact text
) returns void language plpgsql security definer set search_path='' as $$
begin
  if not platform.user_has_system_permission('workspace_settings.manage') then
    raise exception using errcode='P0001',message='SETTINGS_PERMISSION_DENIED';
  end if;
  update platform.workspace_settings set display_name=new_display_name,
    locale=new_locale,timezone=new_timezone,commercial_contact=new_contact,
    updated_by=platform.current_user_id(),updated_at=now()
  where workspace_id=target_workspace;
end $$;

create or replace function platform.update_workspace_subscription(
  target_workspace uuid,plan_code text,new_state text
) returns boolean language plpgsql security definer set search_path='' as $$
declare selected_plan uuid;
begin
  if not platform.user_has_system_permission('subscriptions.manage') then return false; end if;
  select id into selected_plan from platform.plans
  where code=plan_code and status='active';
  if selected_plan is null then return false; end if;
  update platform.workspace_subscriptions set plan_id=selected_plan,
    state=new_state,updated_at=now() where workspace_id=target_workspace;
  return found;
end $$;

drop policy if exists usage_events_runtime_select on platform.usage_events;
create policy usage_events_runtime_select on platform.usage_events
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('usage.read')
);
drop policy if exists governance_runtime_select on platform.governance_settings;
drop policy if exists governance_runtime_update on platform.governance_settings;
create policy governance_runtime_select on platform.governance_settings
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and (
    platform.user_has_workspace_membership(workspace_id)
    or platform.user_has_system_permission('governance.read')
  )
);
create policy governance_runtime_update on platform.governance_settings
for update to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and is_active and platform.user_has_system_permission('governance.manage')
) with check(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and is_active and platform.user_has_system_permission('governance.manage')
);
drop policy if exists audit_events_runtime_select on platform.audit_events;
create policy audit_events_runtime_select on platform.audit_events
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('audit.read')
);
drop policy if exists administrative_operations_runtime_select
  on platform.administrative_operations;
create policy administrative_operations_runtime_select
on platform.administrative_operations for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('operations.read')
);

drop policy if exists plans_runtime_select on platform.plans;
drop policy if exists subscriptions_runtime_select on platform.workspace_subscriptions;
drop policy if exists entitlements_runtime_select on platform.plan_entitlements;
drop policy if exists providers_runtime_select on platform.provider_registry;
drop policy if exists workspace_provider_settings_runtime_select
  on platform.workspace_provider_settings;
drop policy if exists credential_references_runtime_select
  on platform.credential_references;
drop policy if exists workspace_api_keys_runtime_select on platform.workspace_api_keys;
drop policy if exists workspace_security_settings_runtime_select
  on platform.workspace_security_settings;
drop policy if exists workspace_settings_runtime_select on platform.workspace_settings;
create policy plans_runtime_select on platform.plans
for select to knowledge_platform_runtime
using(platform.user_has_system_permission('plans.read'));
create policy subscriptions_runtime_select on platform.workspace_subscriptions
for select to knowledge_platform_runtime using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('subscriptions.read')
);
create policy entitlements_runtime_select on platform.plan_entitlements
for select to knowledge_platform_runtime
using(platform.user_has_system_permission('subscriptions.read'));
create policy providers_runtime_select on platform.provider_registry
for select to knowledge_platform_runtime
using(platform.user_has_system_permission('providers.read'));
create policy workspace_provider_settings_runtime_select
on platform.workspace_provider_settings for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('providers.read')
);
create policy credential_references_runtime_select
on platform.credential_references for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('credentials.read')
);
create policy workspace_api_keys_runtime_select
on platform.workspace_api_keys for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('api_keys.read')
);
create policy workspace_security_settings_runtime_select
on platform.workspace_security_settings for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('security.read')
);
create policy workspace_settings_runtime_select
on platform.workspace_settings for select to knowledge_platform_runtime
using(
  workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid
  and platform.user_has_system_permission('settings.read')
);

-- ---------------------------------------------------------------------------
-- Grants. Browser database roles remain denied; runtime receives only the
-- table/functions needed by the server-side application boundary.
-- ---------------------------------------------------------------------------
grant select on platform.workspace_role_assignment_history,
  platform.invitation_role_migration_history to knowledge_platform_runtime;
grant select,insert,update,delete on platform.system_roles,
  platform.system_role_permissions to knowledge_platform_runtime;
grant select on platform.system_access_assignments to knowledge_platform_runtime;
grant select,insert on platform.system_conversations,
  platform.system_conversation_messages to knowledge_platform_runtime;
revoke all on platform.workspace_role_assignment_history,
  platform.invitation_role_migration_history,platform.system_roles,
  platform.system_role_permissions,platform.system_access_assignments,
  platform.system_conversations,platform.system_conversation_messages
  from anon,authenticated;

revoke all on function platform.user_has_any_system_access() from public;
revoke all on function platform.user_has_system_permission(text) from public;
revoke all on function platform.assign_system_access(uuid,uuid) from public;
revoke all on function platform.revoke_system_access(uuid,uuid) from public;
revoke all on function platform.protect_workspace_role_identity() from public;
revoke all on function platform.protect_workspace_role_permissions() from public;
revoke all on function platform.protect_system_role_identity() from public;
revoke all on function platform.protect_system_role_permissions() from public;
revoke all on function platform.create_workspace_stage1(uuid,text) from public;
revoke all on function platform.update_workspace_operational_state(uuid,text,boolean)
  from public;
revoke all on function platform.rename_workspace_conversation(uuid,uuid,text) from public;
revoke all on function platform.set_workspace_conversation_archived(uuid,uuid,boolean)
  from public;
revoke all on function platform.rename_system_conversation(uuid,text) from public;
revoke all on function platform.set_system_conversation_archived(uuid,boolean)
  from public;

grant execute on function platform.user_has_any_system_access(),
  platform.user_has_system_permission(text),
  platform.assign_system_access(uuid,uuid),
  platform.revoke_system_access(uuid,uuid),
  platform.create_workspace_stage1(uuid,text),
  platform.update_workspace_operational_state(uuid,text,boolean),
  platform.rename_workspace_conversation(uuid,uuid,text),
  platform.set_workspace_conversation_archived(uuid,uuid,boolean),
  platform.rename_system_conversation(uuid,text),
  platform.set_system_conversation_archived(uuid,boolean)
  to knowledge_platform_runtime;

-- Trigger-only functions are intentionally not executable by runtime.
revoke all on function platform.protect_workspace_role_identity()
  from knowledge_platform_runtime;
revoke all on function platform.protect_workspace_role_permissions()
  from knowledge_platform_runtime;
revoke all on function platform.protect_system_role_identity()
  from knowledge_platform_runtime;
revoke all on function platform.protect_system_role_permissions()
  from knowledge_platform_runtime;

-- Revoke legacy direct Workspace-management execution paths that conflict
-- with the final System-authority boundary. Their definitions remain for
-- migration/audit traceability.
revoke execute on function platform.create_workspace_with_owner(uuid,text,uuid)
  from knowledge_platform_runtime;

-- Runtime remains a constrained RLS subject. Deployment does not need role-
-- administration privilege: abort read-only unless the live role is already
-- exactly the approved LOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOBYPASSRLS.
do $stage1_runtime_role_assertion$
begin
  if (
    select count(*)
    from pg_catalog.pg_roles role
    where role.rolname='knowledge_platform_runtime'
      and role.rolcanlogin
      and not role.rolsuper
      and not role.rolcreatedb
      and not role.rolcreaterole
      and not role.rolbypassrls
  )<>1 then
    raise exception using errcode='P0001',
      message='STAGE1_RUNTIME_ROLE_SECURITY_PRECONDITION_FAILED';
  end if;
end
$stage1_runtime_role_assertion$;
