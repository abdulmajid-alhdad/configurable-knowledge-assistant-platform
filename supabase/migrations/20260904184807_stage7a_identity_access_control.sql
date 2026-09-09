-- Stage 7A: authenticated identities, workspace membership, RBAC, teams, invitations.
-- Existing workspaces are intentionally not assigned to any user by this migration.
create extension if not exists citext;

create table platform.user_profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    email citext not null unique,
    display_name text,
    status text not null default 'active' check (status in ('active', 'disabled')),
    created_at timestamptz not null default now(),
    constraint user_profiles_email_nonblank check (btrim(email::text) <> ''),
    constraint user_profiles_display_name_nonblank
        check (display_name is null or btrim(display_name) <> '')
);

create table platform.permissions (
    key text primary key,
    description text not null,
    constraint permissions_key_format check (key ~ '^[a-z]+\.[a-z]+$'),
    constraint permissions_description_nonblank check (btrim(description) <> '')
);

create table platform.roles (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces (id),
    name text not null,
    is_system boolean not null default false,
    created_at timestamptz not null default now(),
    unique (id, workspace_id),
    constraint roles_name_nonblank check (btrim(name) <> '')
);
create unique index roles_workspace_name_unique
    on platform.roles (workspace_id, lower(name));

create table platform.role_permissions (
    role_id uuid not null references platform.roles (id) on delete cascade,
    permission_key text not null references platform.permissions (key),
    primary key (role_id, permission_key)
);

create table platform.workspace_memberships (
    workspace_id uuid not null references platform.workspaces (id),
    user_id uuid not null references auth.users (id),
    role_id uuid not null,
    status text not null default 'active' check (status = 'active'),
    created_at timestamptz not null default now(),
    joined_at timestamptz,
    primary key (workspace_id, user_id),
    foreign key (role_id, workspace_id)
        references platform.roles (id, workspace_id)
);
create index workspace_memberships_user_id_idx
    on platform.workspace_memberships (user_id);
create index workspace_memberships_role_id_idx
    on platform.workspace_memberships (role_id);

create table platform.teams (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces (id),
    name text not null,
    description text,
    created_at timestamptz not null default now(),
    unique (id, workspace_id),
    constraint teams_name_nonblank check (btrim(name) <> ''),
    constraint teams_description_nonblank
        check (description is null or btrim(description) <> '')
);
create unique index teams_workspace_name_unique
    on platform.teams (workspace_id, lower(name));

create table platform.team_members (
    team_id uuid not null,
    workspace_id uuid not null,
    user_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (team_id, user_id),
    foreign key (team_id, workspace_id)
        references platform.teams (id, workspace_id) on delete cascade,
    foreign key (workspace_id, user_id)
        references platform.workspace_memberships (workspace_id, user_id) on delete cascade
);
create index team_members_workspace_user_idx
    on platform.team_members (workspace_id, user_id);

create table platform.invitations (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces (id),
    email citext not null,
    role_id uuid not null,
    invited_by uuid not null references auth.users (id),
    token_hash char(64) not null unique,
    status text not null default 'pending'
        check (status in ('pending', 'accepted', 'revoked')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    accepted_at timestamptz,
    accepted_by uuid references auth.users (id),
    foreign key (role_id, workspace_id)
        references platform.roles (id, workspace_id),
    constraint invitations_email_nonblank check (btrim(email::text) <> ''),
    constraint invitations_expiry_after_creation check (expires_at > created_at),
    constraint invitations_disposition_consistent check (
        (status = 'accepted' and accepted_at is not null and accepted_by is not null)
        or (status <> 'accepted' and accepted_at is null and accepted_by is null)
    )
);
-- Multiple independently revocable links are allowed; token_hash is the replay/
-- identity boundary. This index supports workspace/email administration without
-- making an expired row block a later invitation.
create index invitations_workspace_email_idx
    on platform.invitations (workspace_id, lower(email::text));

insert into platform.permissions (key, description) values
    ('workspace.read', 'Read workspace context'),
    ('workspace.manage', 'Manage workspace and ownership'),
    ('assistant.read', 'Read assistants'),
    ('assistant.create', 'Create assistants'),
    ('assistant.update', 'Update assistants'),
    ('knowledge.read', 'Read knowledge sources'),
    ('knowledge.create', 'Create and upload knowledge sources'),
    ('knowledge.process', 'Process knowledge sources'),
    ('knowledge.attach', 'Attach or detach assistant knowledge'),
    ('conversation.read', 'Read conversations and evidence'),
    ('conversation.ask', 'Create conversations and ask questions'),
    ('evaluation.read', 'Read evaluation suites'),
    ('operations.read', 'Read operations status'),
    ('settings.read', 'Read workspace settings'),
    ('members.read', 'Read workspace members'),
    ('members.manage', 'Manage workspace members'),
    ('teams.read', 'Read workspace teams'),
    ('teams.manage', 'Manage workspace teams'),
    ('roles.read', 'Read roles and permissions'),
    ('roles.manage', 'Manage custom roles and assignments'),
    ('invitations.read', 'Read workspace invitations'),
    ('invitations.manage', 'Create and revoke invitations');

-- System roles are created for legacy workspaces without assigning ownership.
insert into platform.roles (id, workspace_id, name, is_system)
select gen_random_uuid(), workspace.id, role_name, true
from platform.workspaces workspace
cross join unnest(array['OWNER', 'ADMIN', 'MEMBER', 'VIEWER']) role_name;

insert into platform.role_permissions (role_id, permission_key)
select role.id, permission.key
from platform.roles role
cross join platform.permissions permission
where role.is_system and (
    role.name = 'OWNER'
    or (role.name = 'ADMIN' and permission.key not in ('workspace.manage', 'roles.manage'))
    or (role.name = 'MEMBER' and permission.key in (
        'workspace.read', 'assistant.read', 'assistant.create', 'assistant.update',
        'knowledge.read', 'knowledge.create', 'knowledge.process', 'knowledge.attach',
        'conversation.read', 'conversation.ask', 'evaluation.read', 'operations.read',
        'settings.read', 'members.read', 'teams.read', 'roles.read', 'invitations.read'
    ))
    or (role.name = 'VIEWER' and permission.key in (
        'workspace.read', 'assistant.read', 'knowledge.read', 'conversation.read',
        'evaluation.read', 'operations.read', 'settings.read', 'members.read',
        'teams.read', 'roles.read', 'invitations.read'
    ))
);

-- These helpers break membership-policy recursion. They are private-schema,
-- fixed-search-path, explicitly granted, and use only trusted tx-local identity.
create function platform.current_user_id()
returns uuid language sql stable security invoker set search_path = ''
as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

create function platform.user_has_workspace_membership(target_workspace_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from platform.workspace_memberships membership
        where membership.workspace_id = target_workspace_id
          and membership.user_id = platform.current_user_id()
          and membership.status = 'active'
    )
$$;

create function platform.user_has_permission(
    target_workspace_id uuid, required_permission text
)
returns boolean language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1
        from platform.workspace_memberships membership
        join platform.role_permissions assignment on assignment.role_id = membership.role_id
        where membership.workspace_id = target_workspace_id
          and membership.user_id = platform.current_user_id()
          and membership.status = 'active'
          and assignment.permission_key = required_permission
    )
$$;

create function platform.create_workspace_with_owner(
    new_workspace_id uuid, new_workspace_name text, creator_user_id uuid
)
returns void language plpgsql security definer set search_path = ''
as $$
declare
    owner_role_id uuid;
    role_record record;
begin
    if creator_user_id is distinct from platform.current_user_id() then
        raise exception 'workspace creator identity mismatch';
    end if;
    if btrim(new_workspace_name) = '' then
        raise exception 'workspace name is blank';
    end if;

    insert into platform.workspaces (id, name)
    values (new_workspace_id, new_workspace_name);

    for role_record in
        select role_name from unnest(array['OWNER', 'ADMIN', 'MEMBER', 'VIEWER']) role_name
    loop
        insert into platform.roles (id, workspace_id, name, is_system)
        values (gen_random_uuid(), new_workspace_id, role_record.role_name, true)
        returning id into owner_role_id;

        insert into platform.role_permissions (role_id, permission_key)
        select owner_role_id, permission.key from platform.permissions permission
        where role_record.role_name = 'OWNER'
           or (role_record.role_name = 'ADMIN'
               and permission.key not in ('workspace.manage', 'roles.manage'))
           or (role_record.role_name = 'MEMBER' and permission.key in (
               'workspace.read', 'assistant.read', 'assistant.create', 'assistant.update',
               'knowledge.read', 'knowledge.create', 'knowledge.process', 'knowledge.attach',
               'conversation.read', 'conversation.ask', 'evaluation.read', 'operations.read',
               'settings.read', 'members.read', 'teams.read', 'roles.read',
               'invitations.read'))
           or (role_record.role_name = 'VIEWER' and permission.key in (
               'workspace.read', 'assistant.read', 'knowledge.read', 'conversation.read',
               'evaluation.read', 'operations.read', 'settings.read', 'members.read',
               'teams.read', 'roles.read', 'invitations.read'));

        if role_record.role_name = 'OWNER' then
            insert into platform.workspace_memberships (
                workspace_id, user_id, role_id, joined_at
            ) values (new_workspace_id, creator_user_id, owner_role_id, now());
        end if;
    end loop;
end
$$;

-- Final-owner mutation primitives serialize memberships before deciding.
create function platform.change_membership_role(target_workspace uuid, target_user uuid, new_role uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare old_name text; new_name text;
begin
  if not platform.user_has_permission(target_workspace, 'members.manage') then return false; end if;
  perform 1 from platform.workspace_memberships where workspace_id=target_workspace for update;
  select r.name into old_name from platform.workspace_memberships m join platform.roles r on r.id=m.role_id
    where m.workspace_id=target_workspace and m.user_id=target_user;
  select name into new_name from platform.roles where id=new_role and workspace_id=target_workspace;
  if old_name is null or new_name is null then return false; end if;
  if new_name='OWNER' and not platform.user_has_permission(target_workspace,'workspace.manage')
  then raise exception 'owner assignment requires workspace management'; end if;
  if old_name='OWNER' and new_name<>'OWNER' and
     (select count(*) from platform.workspace_memberships m join platform.roles r on r.id=m.role_id
       where m.workspace_id=target_workspace and m.status='active' and r.name='OWNER') <= 1
  then raise exception 'final owner cannot be demoted'; end if;
  update platform.workspace_memberships set role_id=new_role where workspace_id=target_workspace and user_id=target_user;
  return true;
end $$;

create function platform.remove_workspace_member(target_workspace uuid, target_user uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare old_name text;
begin
  if not platform.user_has_permission(target_workspace, 'members.manage') then return false; end if;
  perform 1 from platform.workspace_memberships where workspace_id=target_workspace for update;
  select r.name into old_name from platform.workspace_memberships m join platform.roles r on r.id=m.role_id
    where m.workspace_id=target_workspace and m.user_id=target_user;
  if old_name is null then return false; end if;
  if old_name='OWNER' and
     (select count(*) from platform.workspace_memberships m join platform.roles r on r.id=m.role_id
       where m.workspace_id=target_workspace and m.status='active' and r.name='OWNER') <= 1
  then raise exception 'final owner cannot be removed'; end if;
  delete from platform.workspace_memberships where workspace_id=target_workspace and user_id=target_user;
  return true;
end $$;

create function platform.accept_invitation(expected_hash text, authenticated_email text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare invitation platform.invitations%rowtype;
begin
  select * into invitation from platform.invitations where token_hash=expected_hash for update;
  if invitation.id is null or invitation.status<>'pending' or invitation.expires_at<=now()
     or lower(invitation.email::text)<>lower(authenticated_email)
  then return null; end if;
  if exists(select 1 from platform.workspace_memberships m
      where m.workspace_id=invitation.workspace_id and m.user_id=platform.current_user_id())
  then return null; end if;
  insert into platform.workspace_memberships(workspace_id,user_id,role_id,joined_at)
    values(invitation.workspace_id,platform.current_user_id(),invitation.role_id,now());
  update platform.invitations set status='accepted',accepted_at=now(),accepted_by=platform.current_user_id()
    where id=invitation.id;
  return invitation.workspace_id;
end $$;

create function platform.revoke_invitation(target_workspace uuid, target_invitation uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace,'invitations.manage') then return false; end if;
  update platform.invitations set status='revoked'
    where id=target_invitation and workspace_id=target_workspace and status='pending';
  return found;
end $$;

revoke all on function platform.current_user_id() from public;
revoke all on function platform.user_has_workspace_membership(uuid) from public;
revoke all on function platform.user_has_permission(uuid, text) from public;
revoke all on function platform.create_workspace_with_owner(uuid, text, uuid) from public;
revoke all on function platform.change_membership_role(uuid, uuid, uuid) from public;
revoke all on function platform.remove_workspace_member(uuid, uuid) from public;
revoke all on function platform.accept_invitation(text, text) from public;
revoke all on function platform.revoke_invitation(uuid, uuid) from public;
grant execute on function platform.current_user_id() to knowledge_platform_runtime;
grant execute on function platform.user_has_workspace_membership(uuid)
    to knowledge_platform_runtime;
grant execute on function platform.user_has_permission(uuid, text)
    to knowledge_platform_runtime;
grant execute on function platform.create_workspace_with_owner(uuid, text, uuid)
    to knowledge_platform_runtime;
grant execute on function platform.change_membership_role(uuid, uuid, uuid),
  platform.remove_workspace_member(uuid, uuid), platform.accept_invitation(text, text)
  to knowledge_platform_runtime;
grant execute on function platform.revoke_invitation(uuid, uuid)
  to knowledge_platform_runtime;

alter table platform.user_profiles enable row level security;
alter table platform.user_profiles force row level security;
alter table platform.permissions enable row level security;
alter table platform.permissions force row level security;
alter table platform.roles enable row level security;
alter table platform.roles force row level security;
alter table platform.role_permissions enable row level security;
alter table platform.role_permissions force row level security;
alter table platform.workspace_memberships enable row level security;
alter table platform.workspace_memberships force row level security;
alter table platform.teams enable row level security;
alter table platform.teams force row level security;
alter table platform.team_members enable row level security;
alter table platform.team_members force row level security;
alter table platform.invitations enable row level security;
alter table platform.invitations force row level security;

create policy user_profiles_runtime_select on platform.user_profiles
    for select to knowledge_platform_runtime
    using (
        user_id = platform.current_user_id()
        or exists (
            select 1 from platform.workspace_memberships membership
            where membership.user_id = user_profiles.user_id
              and membership.workspace_id = current_setting('app.workspace_id', true)::uuid
        )
    );
create policy user_profiles_runtime_insert on platform.user_profiles
    for insert to knowledge_platform_runtime
    with check (user_id = platform.current_user_id());
create policy user_profiles_runtime_update on platform.user_profiles
    for update to knowledge_platform_runtime
    using (user_id = platform.current_user_id())
    with check (user_id = platform.current_user_id());

create policy permissions_runtime_select on platform.permissions
    for select to knowledge_platform_runtime using (platform.current_user_id() is not null);

create policy memberships_runtime_select on platform.workspace_memberships
    for select to knowledge_platform_runtime
    using (
        user_id = platform.current_user_id()
        or (
            workspace_id = current_setting('app.workspace_id', true)::uuid
            and platform.user_has_permission(workspace_id, 'members.read')
        )
    );
create policy memberships_runtime_insert on platform.workspace_memberships
    for insert to knowledge_platform_runtime
    with check (false);
create policy memberships_runtime_update on platform.workspace_memberships
    for update to knowledge_platform_runtime
    using (false) with check (false);
create policy memberships_runtime_delete on platform.workspace_memberships
    for delete to knowledge_platform_runtime
    using (false);

create policy roles_runtime_select on platform.roles
    for select to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_workspace_membership(workspace_id)
        and platform.user_has_permission(workspace_id, 'roles.read')
    );
create policy roles_runtime_insert on platform.roles
    for insert to knowledge_platform_runtime
    with check (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'roles.manage')
        and not is_system
    );
create policy roles_runtime_update on platform.roles
    for update to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'roles.manage')
        and not is_system
    )
    with check (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'roles.manage')
        and not is_system
    );
create policy roles_runtime_delete on platform.roles
    for delete to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'roles.manage')
        and not is_system
    );

create policy role_permissions_runtime_select on platform.role_permissions
    for select to knowledge_platform_runtime
    using (exists (
        select 1 from platform.roles role
        where role.id = role_permissions.role_id
          and role.workspace_id = current_setting('app.workspace_id', true)::uuid
          and platform.user_has_permission(role.workspace_id, 'roles.read')
    ));
create policy role_permissions_runtime_manage on platform.role_permissions
    for all to knowledge_platform_runtime
    using (exists (
        select 1 from platform.roles role
        where role.id = role_permissions.role_id and not role.is_system
          and role.workspace_id = current_setting('app.workspace_id', true)::uuid
          and platform.user_has_permission(role.workspace_id, 'roles.manage')
    ))
    with check (exists (
        select 1 from platform.roles role
        where role.id = role_permissions.role_id and not role.is_system
          and role.workspace_id = current_setting('app.workspace_id', true)::uuid
          and role_permissions.permission_key <> 'workspace.manage'
          and platform.user_has_permission(role.workspace_id, 'roles.manage')
    ));

create policy teams_runtime_select on platform.teams
    for select to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'teams.read')
    );
create policy teams_runtime_manage on platform.teams
    for all to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'teams.manage')
    )
    with check (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'teams.manage')
    );
create policy team_members_runtime_select on platform.team_members
    for select to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'teams.read')
    );
create policy team_members_runtime_manage on platform.team_members
    for all to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'teams.manage')
    )
    with check (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'teams.manage')
    );

create policy invitations_runtime_select on platform.invitations
    for select to knowledge_platform_runtime
    using (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and platform.user_has_permission(workspace_id, 'invitations.read')
    );
create policy invitations_runtime_insert on platform.invitations
    for insert to knowledge_platform_runtime
    with check (
        workspace_id = current_setting('app.workspace_id', true)::uuid
        and invited_by = platform.current_user_id()
        and platform.user_has_permission(workspace_id, 'invitations.manage')
        and exists (
          select 1 from platform.roles invitation_role
          where invitation_role.id = invitations.role_id
            and invitation_role.workspace_id = invitations.workspace_id
            and (invitation_role.name <> 'OWNER'
              or platform.user_has_permission(workspace_id, 'workspace.manage'))
        )
    );
create policy invitations_runtime_update on platform.invitations
    for update to knowledge_platform_runtime
    using (false) with check (false);

-- Workspace discovery is now membership-authoritative. Creation still uses a
-- tx-local new workspace ID and is completed atomically with OWNER membership.
drop policy workspaces_runtime_select on platform.workspaces;
drop policy workspaces_runtime_insert on platform.workspaces;
drop policy workspaces_runtime_update on platform.workspaces;
drop policy workspaces_runtime_delete on platform.workspaces;
create policy workspaces_runtime_select on platform.workspaces
    for select to knowledge_platform_runtime
    using (platform.user_has_workspace_membership(id));
create policy workspaces_runtime_insert on platform.workspaces
    for insert to knowledge_platform_runtime with check(false);
create policy workspaces_runtime_update on platform.workspaces
    for update to knowledge_platform_runtime
    using(platform.user_has_permission(id,'workspace.manage'))
    with check(platform.user_has_permission(id,'workspace.manage'));
create policy workspaces_runtime_delete on platform.workspaces
    for delete to knowledge_platform_runtime using(false);

-- Replace Stage 6 workspace-only policies: arbitrary workspace GUC is never sufficient.
drop policy assistants_runtime_select on platform.assistants;
drop policy assistants_runtime_insert on platform.assistants;
drop policy assistants_runtime_update on platform.assistants;
drop policy assistants_runtime_delete on platform.assistants;
create policy assistants_runtime_select on platform.assistants for select to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'assistant.read'));
create policy assistants_runtime_insert on platform.assistants for insert to knowledge_platform_runtime
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'assistant.create'));
create policy assistants_runtime_update on platform.assistants for update to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'assistant.update'))
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'assistant.update'));
create policy assistants_runtime_delete on platform.assistants for delete to knowledge_platform_runtime using(false);

drop policy knowledge_sources_runtime_select on platform.knowledge_sources;
drop policy knowledge_sources_runtime_insert on platform.knowledge_sources;
drop policy knowledge_sources_runtime_update on platform.knowledge_sources;
drop policy knowledge_sources_runtime_delete on platform.knowledge_sources;
create policy knowledge_sources_runtime_select on platform.knowledge_sources for select to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.read'));
create policy knowledge_sources_runtime_insert on platform.knowledge_sources for insert to knowledge_platform_runtime
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.create'));
create policy knowledge_sources_runtime_update on platform.knowledge_sources for update to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.process'))
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.process'));
create policy knowledge_sources_runtime_delete on platform.knowledge_sources for delete to knowledge_platform_runtime using(false);

drop policy conversations_runtime_select on platform.conversations;
drop policy conversations_runtime_insert on platform.conversations;
create policy conversations_runtime_select on platform.conversations for select to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'conversation.read'));
create policy conversations_runtime_insert on platform.conversations for insert to knowledge_platform_runtime
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'conversation.ask'));
drop policy messages_runtime_select on platform.messages;
drop policy messages_runtime_insert on platform.messages;
create policy messages_runtime_select on platform.messages for select to knowledge_platform_runtime using(exists(
  select 1 from platform.conversations c where c.id=messages.conversation_id and platform.user_has_permission(c.workspace_id,'conversation.read')));
create policy messages_runtime_insert on platform.messages for insert to knowledge_platform_runtime with check(exists(
  select 1 from platform.conversations c where c.id=messages.conversation_id and platform.user_has_permission(c.workspace_id,'conversation.ask')));

drop policy assistant_knowledge_sources_runtime_select on platform.assistant_knowledge_sources;
drop policy assistant_knowledge_sources_runtime_insert on platform.assistant_knowledge_sources;
drop policy assistant_knowledge_sources_runtime_delete on platform.assistant_knowledge_sources;
create policy assistant_knowledge_sources_runtime_select on platform.assistant_knowledge_sources for select to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.read'));
create policy assistant_knowledge_sources_runtime_insert on platform.assistant_knowledge_sources for insert to knowledge_platform_runtime
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.attach'));
create policy assistant_knowledge_sources_runtime_delete on platform.assistant_knowledge_sources for delete to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.attach'));

drop policy message_evidence_runtime_select on platform.message_evidence;
drop policy message_evidence_runtime_insert on platform.message_evidence;
create policy message_evidence_runtime_select on platform.message_evidence for select to knowledge_platform_runtime using(exists(
  select 1 from platform.conversations c where c.id=message_evidence.conversation_id and platform.user_has_permission(c.workspace_id,'conversation.read')));
create policy message_evidence_runtime_insert on platform.message_evidence for insert to knowledge_platform_runtime with check(exists(
  select 1 from platform.conversations c join platform.knowledge_sources s on s.id=message_evidence.source_id
  where c.id=message_evidence.conversation_id and s.workspace_id=c.workspace_id and platform.user_has_permission(c.workspace_id,'conversation.ask')));

drop policy representations_workspace on retrieval.document_representations;
drop policy chunks_workspace on retrieval.document_chunks;
create policy representations_workspace on retrieval.document_representations for all to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.read'))
  with check(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'knowledge.process'));
create policy chunks_workspace on retrieval.document_chunks for all to knowledge_platform_runtime using(exists(
  select 1 from retrieval.document_representations r where r.id=document_chunks.representation_id and platform.user_has_permission(r.workspace_id,'knowledge.read')))
  with check(exists(select 1 from retrieval.document_representations r where r.id=document_chunks.representation_id and platform.user_has_permission(r.workspace_id,'knowledge.process')));

drop policy evaluation_runs_workspace on evaluation.evaluation_runs;
drop policy evaluation_results_workspace on evaluation.evaluation_results;
create policy evaluation_runs_workspace on evaluation.evaluation_runs for all to knowledge_platform_runtime
  using(workspace_id=current_setting('app.workspace_id',true)::uuid and platform.user_has_permission(workspace_id,'evaluation.read'))
  with check(false);
create policy evaluation_results_workspace on evaluation.evaluation_results for select to knowledge_platform_runtime using(exists(
  select 1 from evaluation.evaluation_runs r where r.id=evaluation_results.run_id and platform.user_has_permission(r.workspace_id,'evaluation.read')));

grant select, insert, update on table platform.user_profiles
    to knowledge_platform_runtime;
grant select on table platform.permissions to knowledge_platform_runtime;
grant select, insert, update, delete on table platform.roles,
    platform.role_permissions, platform.teams, platform.team_members
    to knowledge_platform_runtime;
grant select on table platform.workspace_memberships to knowledge_platform_runtime;
grant select, insert on table platform.invitations
    to knowledge_platform_runtime;

revoke all on table platform.user_profiles, platform.permissions,
    platform.roles, platform.role_permissions, platform.workspace_memberships,
    platform.teams, platform.team_members, platform.invitations
    from anon, authenticated;
