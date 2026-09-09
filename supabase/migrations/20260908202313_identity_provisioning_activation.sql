-- Backend-only identity provisioning and activation-only invitations.
-- Historical invitation rows remain intact and are deliberately not made
-- activatable without a provisioned Auth identity.

alter table platform.invitations
  add column provisioned_user_id uuid references auth.users (id) on delete restrict,
  add column team_id uuid;

alter table platform.invitations
  add constraint invitations_team_workspace_fkey
  foreign key (team_id, workspace_id)
  references platform.teams (id, workspace_id) on delete restrict;

create unique index invitations_provisioned_user_unique
  on platform.invitations (provisioned_user_id)
  where provisioned_user_id is not null;

create index invitations_workspace_team_idx
  on platform.invitations (workspace_id, team_id)
  where team_id is not null;

create function platform.validate_identity_provisioning(
  target_workspace uuid,
  target_email text,
  target_role uuid,
  target_team uuid,
  target_expiry timestamptz
) returns text
language plpgsql security definer set search_path = '' as $$
declare denial text;
begin
  if not platform.user_has_system_permission('invitations.manage') then
    return 'IDENTITY_ADMIN_PERMISSION_DENIED';
  end if;
  if target_email is null or btrim(target_email) = ''
     or target_expiry is null or target_expiry <= now() then
    return 'PROVISIONING_INPUT_INVALID';
  end if;
  if not exists (
    select 1 from platform.workspaces workspace
    where workspace.id = target_workspace
  ) then
    return 'WORKSPACE_NOT_FOUND';
  end if;
  if not exists (
    select 1 from platform.roles role
    where role.id = target_role
      and role.workspace_id = target_workspace
      and role.status = 'active'
      and (
        (role.role_kind = 'built_in'
         and role.canonical_key in ('WORKSPACE_MANAGER', 'MEMBER'))
        or role.role_kind = 'custom'
      )
      and upper(role.name) <> 'SYSTEM_ADMIN'
  ) then
    return 'WORKSPACE_ROLE_INVALID';
  end if;
  if target_team is not null and not exists (
    select 1 from platform.teams team
    where team.id = target_team and team.workspace_id = target_workspace
  ) then
    return 'TEAM_WORKSPACE_MISMATCH';
  end if;
  if exists (
    select 1 from platform.user_profiles profile
    where lower(profile.email::text) = lower(btrim(target_email))
  ) then
    return 'IDENTITY_ALREADY_EXISTS';
  end if;
  if exists (
    select 1 from platform.invitations invitation
    where lower(invitation.email::text) = lower(btrim(target_email))
      and invitation.status = 'pending'
      and invitation.expires_at > now()
  ) then
    return 'INVITATION_ALREADY_PENDING';
  end if;
  denial := platform.check_invitation_creation(target_workspace, target_expiry);
  return denial;
end $$;

create function platform.create_identity_provisioning_invitation(
  target_workspace uuid,
  target_user uuid,
  target_email text,
  target_display_name text,
  target_role uuid,
  target_team uuid,
  expected_hash text,
  target_expiry timestamptz
) returns table(
  created_invitation_id uuid,
  created_workspace_id uuid,
  created_user_id uuid,
  created_team_id uuid,
  created_status text,
  created_at timestamptz,
  expires_at timestamptz
)
language plpgsql security definer set search_path = '' as $$
declare invitation_id uuid := gen_random_uuid();
declare denial text;
begin
  denial := platform.validate_identity_provisioning(
    target_workspace, target_email, target_role, target_team, target_expiry
  );
  if denial is not null then
    raise exception using errcode = 'P0001', message = denial;
  end if;
  if target_user is null or target_display_name is null
     or btrim(target_display_name) = ''
     or expected_hash is null or char_length(expected_hash) <> 64 then
    raise exception using errcode = 'P0001', message = 'PROVISIONING_INPUT_INVALID';
  end if;
  if not exists (
    select 1 from auth.users identity
    where identity.id = target_user
      and lower(identity.email) = lower(btrim(target_email))
  ) then
    raise exception using errcode = 'P0001', message = 'IDENTITY_PROVIDER_MISMATCH';
  end if;

  insert into platform.user_profiles (user_id, email, display_name, status)
  values (target_user, lower(btrim(target_email)), btrim(target_display_name), 'active');

  insert into platform.invitations (
    id, workspace_id, email, role_id, invited_by, token_hash,
    expires_at, provisioned_user_id, team_id
  ) values (
    invitation_id, target_workspace, lower(btrim(target_email)), target_role,
    platform.current_user_id(), expected_hash, target_expiry, target_user, target_team
  );

  perform platform.append_audit_event(
    target_workspace, 'identity.user_provisioned', 'user_profile', target_user,
    'succeeded', '',
    jsonb_build_object('role_id', target_role, 'team_id', target_team)
  );
  perform platform.append_audit_event(
    target_workspace, 'invitation.created', 'invitation', invitation_id,
    'succeeded', '',
    jsonb_build_object('role_id', target_role, 'team_id', target_team,
                       'provisioned_user_id', target_user)
  );

  return query
  select invitation.id, invitation.workspace_id, invitation.provisioned_user_id,
         invitation.team_id, invitation.status, invitation.created_at,
         invitation.expires_at
  from platform.invitations invitation
  where invitation.id = invitation_id;
end $$;

create function platform.preview_identity_activation(expected_hash text)
returns table(
  invitation_id uuid,
  provisioned_user_id uuid,
  email text,
  display_name text,
  workspace_id uuid,
  workspace_name text,
  role_id uuid,
  role_name text,
  team_id uuid,
  team_name text,
  invitation_status text,
  expires_at timestamptz,
  error_code text
)
language sql stable security definer set search_path = '' as $$
  select invitation.id,
         invitation.provisioned_user_id,
         invitation.email::text,
         profile.display_name,
         invitation.workspace_id,
         workspace.name,
         invitation.role_id,
         role.name,
         invitation.team_id,
         team.name,
         invitation.status,
         invitation.expires_at,
         case
           when invitation.id is null then 'INVITATION_INVALID'
           when invitation.provisioned_user_id is null then 'INVITATION_NOT_ACTIVATABLE'
           when invitation.status = 'accepted' then 'INVITATION_ALREADY_ACCEPTED'
           when invitation.status = 'revoked' then 'INVITATION_REVOKED'
           when invitation.status <> 'pending' then 'INVITATION_INVALID'
           when invitation.expires_at <= now() then 'INVITATION_EXPIRED'
           when identity.id is null or profile.user_id is null then 'PROVISIONED_IDENTITY_MISSING'
           when role.id is null then 'WORKSPACE_ROLE_INVALID'
           when invitation.team_id is not null and team.id is null then 'TEAM_WORKSPACE_MISMATCH'
           else null
         end
  from (select 1) seed
  left join platform.invitations invitation
    on invitation.token_hash = expected_hash
  left join auth.users identity
    on identity.id = invitation.provisioned_user_id
   and lower(identity.email) = lower(invitation.email::text)
  left join platform.user_profiles profile
    on profile.user_id = invitation.provisioned_user_id
   and lower(profile.email::text) = lower(invitation.email::text)
  left join platform.workspaces workspace
    on workspace.id = invitation.workspace_id
  left join platform.roles role
    on role.id = invitation.role_id
   and role.workspace_id = invitation.workspace_id
   and role.status = 'active'
   and (
     (role.role_kind = 'built_in'
      and role.canonical_key in ('WORKSPACE_MANAGER', 'MEMBER'))
     or role.role_kind = 'custom'
   )
   and upper(role.name) <> 'SYSTEM_ADMIN'
  left join platform.teams team
    on team.id = invitation.team_id
   and team.workspace_id = invitation.workspace_id;
$$;

create function platform.activate_identity_provisioning(
  expected_hash text,
  expected_user uuid
) returns table(
  activated_workspace_id uuid,
  activated_user_id uuid,
  activated_team_id uuid,
  error_code text
)
language plpgsql security definer set search_path = '' as $$
declare invitation platform.invitations%rowtype;
declare active_members bigint;
declare denial text;
begin
  select candidate.* into invitation
  from platform.invitations candidate
  where candidate.token_hash = expected_hash
  for update;

  if invitation.id is null then
    error_code := 'INVITATION_INVALID'; return next; return;
  end if;
  if invitation.provisioned_user_id is null
     or invitation.provisioned_user_id <> expected_user then
    error_code := 'INVITATION_NOT_ACTIVATABLE'; return next; return;
  end if;
  if invitation.status = 'accepted' then
    error_code := 'INVITATION_ALREADY_ACCEPTED'; return next; return;
  end if;
  if invitation.status = 'revoked' then
    error_code := 'INVITATION_REVOKED'; return next; return;
  end if;
  if invitation.status <> 'pending' then
    error_code := 'INVITATION_INVALID'; return next; return;
  end if;
  if invitation.expires_at <= now() then
    error_code := 'INVITATION_EXPIRED'; return next; return;
  end if;
  if not exists (
    select 1 from auth.users identity
    join platform.user_profiles profile on profile.user_id = identity.id
    where identity.id = invitation.provisioned_user_id
      and lower(identity.email) = lower(invitation.email::text)
      and lower(profile.email::text) = lower(invitation.email::text)
  ) then
    error_code := 'PROVISIONED_IDENTITY_MISSING'; return next; return;
  end if;
  if not exists (
    select 1 from platform.roles role
    where role.id = invitation.role_id
      and role.workspace_id = invitation.workspace_id
      and role.status = 'active'
      and (
        (role.role_kind = 'built_in'
         and role.canonical_key in ('WORKSPACE_MANAGER', 'MEMBER'))
        or role.role_kind = 'custom'
      )
      and upper(role.name) <> 'SYSTEM_ADMIN'
  ) then
    error_code := 'WORKSPACE_ROLE_INVALID'; return next; return;
  end if;
  if invitation.team_id is not null and not exists (
    select 1 from platform.teams team
    where team.id = invitation.team_id
      and team.workspace_id = invitation.workspace_id
  ) then
    error_code := 'TEAM_WORKSPACE_MISMATCH'; return next; return;
  end if;
  if exists (
    select 1 from platform.workspace_memberships membership
    where membership.workspace_id = invitation.workspace_id
      and membership.user_id = invitation.provisioned_user_id
  ) then
    error_code := 'MEMBERSHIP_ALREADY_EXISTS'; return next; return;
  end if;

  select count(*) into active_members
  from platform.workspace_memberships membership
  where membership.workspace_id = invitation.workspace_id
    and membership.status = 'active';
  denial := platform.stage7c_entitlement_decision(
    invitation.workspace_id, 'max_workspace_members', active_members
  );
  if denial is not null then
    error_code := denial; return next; return;
  end if;

  insert into platform.workspace_memberships (
    workspace_id, user_id, role_id, status, joined_at
  ) values (
    invitation.workspace_id, invitation.provisioned_user_id,
    invitation.role_id, 'active', now()
  );

  if invitation.team_id is not null then
    insert into platform.team_members (team_id, workspace_id, user_id)
    values (invitation.team_id, invitation.workspace_id,
            invitation.provisioned_user_id);
  end if;

  update platform.invitations
  set status = 'accepted', accepted_at = now(),
      accepted_by = invitation.provisioned_user_id
  where id = invitation.id and status = 'pending';

  insert into platform.audit_events (
    workspace_id, actor_user_id, action, resource_type, resource_id,
    outcome, metadata
  ) values (
    invitation.workspace_id, invitation.provisioned_user_id,
    'membership.activated', 'membership', invitation.provisioned_user_id,
    'succeeded', jsonb_build_object('provenance', 'activation_token',
                                    'role_id', invitation.role_id)
  );
  if invitation.team_id is not null then
    insert into platform.audit_events (
      workspace_id, actor_user_id, action, resource_type, resource_id,
      outcome, metadata
    ) values (
      invitation.workspace_id, invitation.provisioned_user_id,
      'team.member_added', 'team', invitation.team_id, 'succeeded',
      jsonb_build_object('provenance', 'activation_token',
                         'member_id', invitation.provisioned_user_id)
    );
  end if;

  activated_workspace_id := invitation.workspace_id;
  activated_user_id := invitation.provisioned_user_id;
  activated_team_id := invitation.team_id;
  error_code := null;
  return next;
end $$;

revoke all on function platform.validate_identity_provisioning(
  uuid, text, uuid, uuid, timestamptz
) from public, anon, authenticated;
revoke all on function platform.create_identity_provisioning_invitation(
  uuid, uuid, text, text, uuid, uuid, text, timestamptz
) from public, anon, authenticated;
revoke all on function platform.preview_identity_activation(text)
  from public, anon, authenticated;
revoke all on function platform.activate_identity_provisioning(text, uuid)
  from public, anon, authenticated;

grant execute on function platform.validate_identity_provisioning(
  uuid, text, uuid, uuid, timestamptz
) to knowledge_platform_runtime;
grant execute on function platform.create_identity_provisioning_invitation(
  uuid, uuid, text, text, uuid, uuid, text, timestamptz
) to knowledge_platform_runtime;
grant execute on function platform.preview_identity_activation(text)
  to knowledge_platform_runtime;
grant execute on function platform.activate_identity_provisioning(text, uuid)
  to knowledge_platform_runtime;
