-- Stage 7C: internal commercial state and advanced administration.
-- FREE entitlements use NULL as an explicit unlimited value. No payment,
-- provider-secret, product-content, or retrieval data is rewritten.

-- Stage 7A allowed only single lowercase words in each permission segment.
-- Stage 7C retains the canonical namespace.action shape while allowing
-- lowercase underscore-separated words within either segment.
alter table platform.permissions
  drop constraint permissions_key_format;
alter table platform.permissions
  add constraint permissions_key_format
  check (key ~ '^[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*$');

insert into platform.permissions (key, description) values
  ('plans.read', 'Read the internal plan catalogue'),
  ('subscriptions.read', 'Read workspace subscription and entitlement state'),
  ('subscriptions.manage', 'Manage internally administered subscription state'),
  ('providers.read', 'Read workspace provider metadata'),
  ('providers.manage', 'Manage workspace provider metadata'),
  ('credentials.read', 'Read credential-reference metadata'),
  ('credentials.manage', 'Manage credential references without secret values'),
  ('api_keys.read', 'Read workspace API-key metadata'),
  ('api_keys.manage', 'Create and revoke scoped workspace API keys'),
  ('security.read', 'Read workspace security controls'),
  ('security.manage', 'Manage enforceable workspace security controls'),
  ('workspace_settings.manage', 'Manage workspace configuration');

insert into platform.role_permissions (role_id, permission_key)
select role.id, permission.key
from platform.roles role
join platform.permissions permission on
  role.name in ('OWNER', 'ADMIN')
  and permission.key in (
    'plans.read','subscriptions.read','subscriptions.manage',
    'providers.read','providers.manage','credentials.read','credentials.manage',
    'api_keys.read','api_keys.manage','security.read','security.manage',
    'workspace_settings.manage'
  );

create table platform.plans (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (code ~ '^[A-Z][A-Z0-9_]{1,39}$'),
  name text not null,
  description text,
  status text not null default 'active' check (status in ('active','archived')),
  billing_interval text check (billing_interval in ('month','year')),
  price_amount numeric(20,4),
  currency text check (currency is null or currency ~ '^[A-Z]{3}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (price_amount is null or price_amount >= 0),
  check ((price_amount is null and currency is null)
      or (price_amount is not null and currency is not null))
);

create table platform.workspace_subscriptions (
  workspace_id uuid primary key references platform.workspaces(id) on delete cascade,
  plan_id uuid not null references platform.plans(id),
  state text not null default 'active'
    check (state in ('active','trialing','past_due','suspended','cancelled')),
  starts_at timestamptz not null default now(),
  ends_at timestamptz,
  external_reference text,
  billing_contact text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (ends_at is null or ends_at >= starts_at)
);

create table platform.plan_entitlements (
  plan_id uuid not null references platform.plans(id) on delete cascade,
  entitlement_key text not null check (entitlement_key ~ '^[a-z][a-z0-9_.]{2,79}$'),
  -- NULL is the sole unlimited representation; non-NULL values are finite.
  limit_value bigint check (limit_value is null or limit_value >= 0),
  unit text not null check (unit ~ '^[a-z][a-z0-9_.]{0,39}$'),
  primary key (plan_id, entitlement_key)
);

create table platform.provider_registry (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (code ~ '^[a-z][a-z0-9_.-]{1,59}$'),
  display_name text not null,
  provider_type text not null check (provider_type in ('generation','embeddings','multi')),
  base_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table platform.workspace_provider_settings (
  workspace_id uuid not null references platform.workspaces(id) on delete cascade,
  provider_code text not null references platform.provider_registry(code),
  enabled boolean not null default true,
  administrative_status text not null default 'configured'
    check (administrative_status in ('configured','disabled','degraded')),
  base_url_override text check (
    base_url_override is null or base_url_override ~ '^https://[^[:space:]]+$'
  ),
  updated_by uuid references auth.users(id),
  updated_at timestamptz not null default now(),
  primary key (workspace_id, provider_code)
);

create table platform.credential_references (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces(id) on delete cascade,
  name text not null check (name ~ '^[A-Z][A-Z0-9_]{1,79}$'),
  provider_code text references platform.provider_registry(code),
  -- References only. Plaintext provider credentials do not satisfy this format.
  secret_reference text not null check (
    secret_reference ~ '^(env:[A-Z][A-Z0-9_]{1,79}|vault:[A-Za-z0-9_./-]{1,180})$'
  ),
  status text not null default 'configured'
    check (status in ('configured','disabled','invalid')),
  updated_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, name)
);

create table platform.workspace_api_keys (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  key_prefix text not null check (key_prefix ~ '^kp_[a-z0-9]{6,20}$'),
  fingerprint text not null check (char_length(fingerprint) between 16 and 128),
  secret_hash text not null check (char_length(secret_hash) = 64),
  scopes text[] not null check (cardinality(scopes) > 0),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz,
  unique (workspace_id, fingerprint)
);

create table platform.workspace_security_settings (
  workspace_id uuid primary key references platform.workspaces(id) on delete cascade,
  api_keys_enabled boolean not null default true,
  invitations_enabled boolean not null default true,
  max_invitation_expiry_days integer not null default 14
    check (max_invitation_expiry_days between 1 and 90),
  updated_by uuid references auth.users(id),
  updated_at timestamptz not null default now()
);

create table platform.workspace_settings (
  workspace_id uuid primary key references platform.workspaces(id) on delete cascade,
  display_name text,
  locale text not null default 'ar',
  timezone text not null default 'Asia/Riyadh',
  commercial_contact text,
  updated_by uuid references auth.users(id),
  updated_at timestamptz not null default now()
);

create index workspace_subscriptions_plan_idx
  on platform.workspace_subscriptions(plan_id);
create index workspace_provider_settings_provider_idx
  on platform.workspace_provider_settings(provider_code);
create index workspace_provider_settings_updated_by_idx
  on platform.workspace_provider_settings(updated_by) where updated_by is not null;
create index credential_references_workspace_idx
  on platform.credential_references(workspace_id);
create index credential_references_provider_idx
  on platform.credential_references(provider_code) where provider_code is not null;
create index credential_references_updated_by_idx
  on platform.credential_references(updated_by) where updated_by is not null;
create index workspace_api_keys_workspace_idx
  on platform.workspace_api_keys(workspace_id, created_at desc);
create index workspace_api_keys_active_idx
  on platform.workspace_api_keys(workspace_id, expires_at)
  where revoked_at is null;
create unique index workspace_api_keys_fingerprint_unique
  on platform.workspace_api_keys(fingerprint);
create index workspace_api_keys_created_by_idx
  on platform.workspace_api_keys(created_by);
create index workspace_security_settings_updated_by_idx
  on platform.workspace_security_settings(updated_by) where updated_by is not null;
create index workspace_settings_updated_by_idx
  on platform.workspace_settings(updated_by) where updated_by is not null;

insert into platform.plans (code, name, description)
values (
  'FREE', 'الخطة المجانية',
  'خطة داخلية افتراضية بلا فوترة أو تحصيل خارجي'
);

-- Stage 7C establishes enforceable dimensions, not arbitrary pricing policy.
-- All legacy/default FREE dimensions therefore begin explicitly unlimited.
insert into platform.plan_entitlements (plan_id, entitlement_key, limit_value, unit)
select plan.id, limit_row.entitlement_key, limit_row.limit_value, limit_row.unit
from platform.plans plan
cross join (values
  ('max_assistants', null::bigint, 'count'),
  ('max_knowledge_sources', null::bigint, 'count'),
  ('max_workspace_members', null::bigint, 'count'),
  ('max_teams', null::bigint, 'count'),
  ('max_custom_roles', null::bigint, 'count'),
  ('max_api_keys', null::bigint, 'count')
) limit_row(entitlement_key, limit_value, unit)
where plan.code = 'FREE';

insert into platform.provider_registry (code, display_name, provider_type, base_url)
values ('openrouter', 'OpenRouter', 'generation', null);

insert into platform.workspace_subscriptions (workspace_id, plan_id)
select workspace.id, plan.id
from platform.workspaces workspace
cross join platform.plans plan
where plan.code = 'FREE';

insert into platform.workspace_provider_settings (workspace_id, provider_code)
select workspace.id, provider.code
from platform.workspaces workspace
cross join platform.provider_registry provider;

insert into platform.workspace_security_settings (workspace_id)
select id from platform.workspaces;
insert into platform.workspace_settings (workspace_id)
select id from platform.workspaces;

create function platform.stage7c_seed_defaults()
returns trigger language plpgsql security definer set search_path = '' as $$
declare free_plan uuid;
begin
  select id into strict free_plan
  from platform.plans where code = 'FREE' and status = 'active';
  insert into platform.workspace_subscriptions(workspace_id, plan_id)
    values (new.id, free_plan);
  insert into platform.workspace_provider_settings(workspace_id, provider_code)
    select new.id, code from platform.provider_registry;
  insert into platform.workspace_security_settings(workspace_id) values (new.id);
  insert into platform.workspace_settings(workspace_id) values (new.id);
  return new;
end $$;
create trigger stage7c_seed_defaults_after_workspace
after insert on platform.workspaces
for each row execute function platform.stage7c_seed_defaults();

-- Internal decision primitive. It serializes all count-limited mutation paths
-- on the workspace subscription row. It is not executable by the runtime role.
create function platform.stage7c_entitlement_decision(
  target_workspace uuid, requested_key text, current_count bigint
) returns text language plpgsql security definer set search_path = '' as $$
declare subscription_state text;
declare configured_limit bigint;
declare measured_count bigint;
begin
  -- Consistent per-workspace/per-entitlement lock ordering prevents two
  -- concurrent creates from both observing the same pre-insert count.
  perform pg_advisory_xact_lock(
    hashtextextended(target_workspace::text || ':' || requested_key, 0)
  );
  select subscription.state, entitlement.limit_value
    into subscription_state, configured_limit
  from platform.workspace_subscriptions subscription
  join platform.plan_entitlements entitlement
    on entitlement.plan_id = subscription.plan_id
  where subscription.workspace_id = target_workspace
    and entitlement.entitlement_key = requested_key
  for update of subscription;

  if not found then return 'ENTITLEMENT_NOT_CONFIGURED'; end if;
  if subscription_state not in ('active','trialing') then
    return 'SUBSCRIPTION_INACTIVE';
  end if;

  if requested_key = 'max_assistants' then
    select count(*) into measured_count from platform.assistants
      where workspace_id=target_workspace;
  elsif requested_key = 'max_knowledge_sources' then
    select count(*) into measured_count from platform.knowledge_sources
      where workspace_id=target_workspace;
  elsif requested_key = 'max_workspace_members' then
    select count(*) into measured_count from platform.workspace_memberships
      where workspace_id=target_workspace and status='active';
  elsif requested_key = 'max_teams' then
    select count(*) into measured_count from platform.teams
      where workspace_id=target_workspace;
  elsif requested_key = 'max_custom_roles' then
    select count(*) into measured_count from platform.roles
      where workspace_id=target_workspace and not is_system;
  elsif requested_key = 'max_api_keys' then
    select count(*) into measured_count from platform.workspace_api_keys
      where workspace_id=target_workspace and revoked_at is null
        and (expires_at is null or expires_at>now());
  else
    return 'ENTITLEMENT_NOT_CONFIGURED';
  end if;

  -- The supplied measurement is retained as a consistency floor for callers,
  -- while the post-lock authoritative query is always decisive.
  measured_count := greatest(measured_count, current_count);
  if configured_limit is not null and measured_count >= configured_limit then
    return 'ENTITLEMENT_LIMIT_REACHED';
  end if;
  return null;
end $$;

create function platform.check_workspace_entitlement(
  target_workspace uuid, requested_key text, current_count bigint
) returns text language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_workspace_membership(target_workspace) then
    return 'WORKSPACE_MEMBERSHIP_REQUIRED';
  end if;
  return platform.stage7c_entitlement_decision(
    target_workspace, requested_key, current_count
  );
end $$;

create function platform.resolve_entitlement(
  target_workspace uuid, requested_key text
) returns bigint language plpgsql security definer stable set search_path = '' as $$
declare result bigint;
begin
  if not platform.user_has_workspace_membership(target_workspace) then
    raise exception 'workspace membership required';
  end if;
  select entitlement.limit_value into result
  from platform.workspace_subscriptions subscription
  join platform.plan_entitlements entitlement
    on entitlement.plan_id = subscription.plan_id
  where subscription.workspace_id = target_workspace
    and entitlement.entitlement_key = requested_key;
  return result;
end $$;

create function platform.stage7c_enforce_count_limit()
returns trigger language plpgsql security definer set search_path = '' as $$
declare entitlement text;
declare measured bigint;
declare denial text;
begin
  if tg_table_name = 'assistants' then
    entitlement := 'max_assistants';
    select count(*) into measured from platform.assistants
      where workspace_id = new.workspace_id;
  elsif tg_table_name = 'knowledge_sources' then
    entitlement := 'max_knowledge_sources';
    select count(*) into measured from platform.knowledge_sources
      where workspace_id = new.workspace_id;
  elsif tg_table_name = 'teams' then
    entitlement := 'max_teams';
    select count(*) into measured from platform.teams
      where workspace_id = new.workspace_id;
  elsif tg_table_name = 'roles' then
    if new.is_system then return new; end if;
    entitlement := 'max_custom_roles';
    select count(*) into measured from platform.roles
      where workspace_id = new.workspace_id and not is_system;
  elsif tg_table_name = 'workspace_memberships' then
    if new.status <> 'active'
       or (tg_op = 'UPDATE' and old.status = 'active') then return new; end if;
    entitlement := 'max_workspace_members';
    select count(*) into measured from platform.workspace_memberships
      where workspace_id = new.workspace_id and status = 'active';
  else
    raise exception 'unsupported Stage 7C entitlement trigger target';
  end if;

  denial := platform.stage7c_entitlement_decision(
    new.workspace_id, entitlement, measured
  );
  if denial is not null then
    raise exception using errcode = 'P0001', message = denial;
  end if;
  return new;
end $$;

create trigger stage7c_assistant_limit_before_insert
before insert on platform.assistants for each row
execute function platform.stage7c_enforce_count_limit();
create trigger stage7c_knowledge_source_limit_before_insert
before insert on platform.knowledge_sources for each row
execute function platform.stage7c_enforce_count_limit();
create trigger stage7c_team_limit_before_insert
before insert on platform.teams for each row
execute function platform.stage7c_enforce_count_limit();
create trigger stage7c_custom_role_limit_before_insert
before insert on platform.roles for each row
execute function platform.stage7c_enforce_count_limit();
create trigger stage7c_member_limit_before_insert
before insert on platform.workspace_memberships for each row
execute function platform.stage7c_enforce_count_limit();
create trigger stage7c_member_limit_before_activation
before update of status on platform.workspace_memberships for each row
execute function platform.stage7c_enforce_count_limit();

create function platform.check_invitation_creation(
  target_workspace uuid, requested_expiry timestamptz
) returns text language plpgsql security definer set search_path = '' as $$
declare settings platform.workspace_security_settings%rowtype;
begin
  if not platform.user_has_permission(target_workspace, 'invitations.manage') then
    return 'SECURITY_POLICY_DENIED';
  end if;
  select * into settings from platform.workspace_security_settings
    where workspace_id = target_workspace;
  if not found or not settings.invitations_enabled then
    return 'SECURITY_POLICY_DENIED';
  end if;
  if requested_expiry > now() + make_interval(days => settings.max_invitation_expiry_days) then
    return 'INVITATION_EXPIRY_EXCEEDS_POLICY';
  end if;
  return null;
end $$;

create function platform.stage7c_enforce_invitation_policy()
returns trigger language plpgsql security definer set search_path = '' as $$
declare denial text;
begin
  denial := platform.check_invitation_creation(new.workspace_id, new.expires_at);
  if denial is not null then
    raise exception using errcode = 'P0001', message = denial;
  end if;
  return new;
end $$;
create trigger stage7c_invitation_policy_before_insert
before insert on platform.invitations for each row
execute function platform.stage7c_enforce_invitation_policy();

-- The application uses this result-bearing Stage 7C boundary so a rejected
-- entitlement can be committed to Audit without consuming the invitation.
create function platform.accept_invitation_stage7c(
  expected_hash text, authenticated_email text
) returns table(accepted_workspace uuid, error_code text)
language plpgsql security definer set search_path = '' as $$
declare invitation platform.invitations%rowtype;
declare active_members bigint;
declare denial text;
begin
  select * into invitation from platform.invitations
    where token_hash = expected_hash for update;
  if invitation.id is null or invitation.status <> 'pending'
     or invitation.expires_at <= now()
     or lower(invitation.email::text) <> lower(authenticated_email)
  then
    accepted_workspace := null; error_code := 'INVITATION_INVALID';
    return next; return;
  end if;
  if exists (
    select 1 from platform.workspace_memberships membership
    where membership.workspace_id = invitation.workspace_id
      and membership.user_id = platform.current_user_id()
  ) then
    accepted_workspace := null; error_code := 'MEMBERSHIP_ALREADY_EXISTS';
    return next; return;
  end if;

  select count(*) into active_members from platform.workspace_memberships
    where workspace_id = invitation.workspace_id and status = 'active';
  denial := platform.stage7c_entitlement_decision(
    invitation.workspace_id, 'max_workspace_members', active_members
  );
  if denial is not null then
    insert into platform.audit_events (
      workspace_id, actor_user_id, action, resource_type, resource_id,
      outcome, metadata
    ) values (
      invitation.workspace_id, platform.current_user_id(),
      'invitation.accept_denied', 'invitation', invitation.id, 'denied',
      jsonb_build_object('reason', denial)
    );
    accepted_workspace := null; error_code := denial;
    return next; return;
  end if;

  insert into platform.workspace_memberships(workspace_id,user_id,role_id,joined_at)
    values(invitation.workspace_id,platform.current_user_id(),invitation.role_id,now());
  update platform.invitations set status='accepted',accepted_at=now(),
    accepted_by=platform.current_user_id() where id=invitation.id;
  accepted_workspace := invitation.workspace_id; error_code := null;
  return next;
end $$;

-- Preserve the Stage 7A SQL signature for compatibility. The running
-- application calls the richer Stage 7C boundary above.
create or replace function platform.accept_invitation(
  expected_hash text, authenticated_email text
) returns uuid language sql security definer set search_path = '' as $$
  select result.accepted_workspace
  from platform.accept_invitation_stage7c(expected_hash, authenticated_email) result
$$;

create function platform.check_api_key_creation(target_workspace uuid)
returns text language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace, 'api_keys.manage') then
    return 'API_KEY_PERMISSION_DENIED';
  end if;
  if not coalesce((
    select api_keys_enabled from platform.workspace_security_settings
    where workspace_id = target_workspace
  ), false) then return 'SECURITY_POLICY_DENIED'; end if;
  return platform.stage7c_entitlement_decision(
    target_workspace, 'max_api_keys', 0
  );
end $$;

create function platform.create_workspace_api_key(
  target_workspace uuid, key_name text, key_prefix_value text,
  key_fingerprint_value text, key_hash text, key_scopes text[],
  key_expires_at timestamptz
) returns uuid language plpgsql security definer set search_path = '' as $$
declare key_id uuid;
declare denial text;
begin
  denial := platform.check_api_key_creation(target_workspace);
  if denial is not null then
    raise exception using errcode = 'P0001', message = denial;
  end if;
  if exists (
    select 1 from unnest(key_scopes) scope
    where not platform.user_has_permission(target_workspace, scope)
  ) then raise exception using errcode='P0001', message='API_KEY_SCOPE_DENIED'; end if;
  insert into platform.workspace_api_keys(
    workspace_id,name,key_prefix,fingerprint,secret_hash,scopes,created_by,expires_at
  ) values (
    target_workspace,key_name,key_prefix_value,key_fingerprint_value,key_hash,
    key_scopes,platform.current_user_id(),key_expires_at
  ) returning id into key_id;
  return key_id;
end $$;

create function platform.revoke_workspace_api_key(target_workspace uuid, target_key uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace, 'api_keys.manage') then
    return false;
  end if;
  update platform.workspace_api_keys set revoked_at = coalesce(revoked_at, now())
  where id = target_key and workspace_id = target_workspace and revoked_at is null;
  return found;
end $$;

create function platform.lookup_workspace_api_key(candidate_fingerprint text)
returns table(
  key_id uuid, workspace_id uuid, scopes text[], created_by uuid,
  secret_hash text
) language sql security definer stable set search_path = '' as $$
  select key.id,key.workspace_id,key.scopes,key.created_by,key.secret_hash
  from platform.workspace_api_keys key
  where key.fingerprint = candidate_fingerprint
    and key.revoked_at is null
    and (key.expires_at is null or key.expires_at > now())
$$;

create function platform.touch_workspace_api_key(target_key uuid)
returns void language sql security definer set search_path = '' as $$
  update platform.workspace_api_keys set last_used_at=now()
  where id=target_key and revoked_at is null
    and (expires_at is null or expires_at > now())
$$;

create function platform.update_workspace_provider(
  target_workspace uuid, target_provider text, new_enabled boolean,
  new_status text, new_base_url text
) returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace, 'providers.manage') then
    return false;
  end if;
  update platform.workspace_provider_settings
    set enabled=new_enabled, administrative_status=new_status,
        base_url_override=new_base_url, updated_by=platform.current_user_id(),
        updated_at=now()
  where workspace_id=target_workspace and provider_code=target_provider;
  return found;
end $$;

create function platform.save_credential_reference(
  target_workspace uuid, reference_name text, target_provider text,
  target_reference text, new_status text
) returns uuid language plpgsql security definer set search_path = '' as $$
declare reference_id uuid;
begin
  if not platform.user_has_permission(target_workspace, 'credentials.manage') then
    raise exception using errcode='P0001', message='CREDENTIAL_PERMISSION_DENIED';
  end if;
  insert into platform.credential_references(
    workspace_id,name,provider_code,secret_reference,status,updated_by
  ) values (
    target_workspace,reference_name,target_provider,target_reference,new_status,
    platform.current_user_id()
  ) on conflict (workspace_id,name) do update set
    provider_code=excluded.provider_code,
    secret_reference=excluded.secret_reference,
    status=excluded.status,
    updated_by=excluded.updated_by,
    updated_at=now()
  returning id into reference_id;
  return reference_id;
end $$;

create function platform.delete_credential_reference(
  target_workspace uuid, target_reference uuid
) returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace, 'credentials.manage') then
    return false;
  end if;
  delete from platform.credential_references
    where workspace_id=target_workspace and id=target_reference;
  return found;
end $$;

create function platform.update_workspace_security(
  target_workspace uuid, keys_enabled boolean, invites_enabled boolean,
  expiry_days integer
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace, 'security.manage') then
    raise exception using errcode='P0001', message='SECURITY_PERMISSION_DENIED';
  end if;
  update platform.workspace_security_settings set
    api_keys_enabled=keys_enabled, invitations_enabled=invites_enabled,
    max_invitation_expiry_days=expiry_days,
    updated_by=platform.current_user_id(), updated_at=now()
  where workspace_id=target_workspace;
end $$;

create function platform.update_workspace_settings(
  target_workspace uuid, new_display_name text, new_locale text,
  new_timezone text, new_contact text
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_permission(target_workspace, 'workspace_settings.manage') then
    raise exception using errcode='P0001', message='SETTINGS_PERMISSION_DENIED';
  end if;
  update platform.workspace_settings set display_name=new_display_name,
    locale=new_locale, timezone=new_timezone, commercial_contact=new_contact,
    updated_by=platform.current_user_id(), updated_at=now()
  where workspace_id=target_workspace;
end $$;

create function platform.update_workspace_subscription(
  target_workspace uuid, plan_code text, new_state text
) returns boolean language plpgsql security definer set search_path = '' as $$
declare selected_plan uuid;
begin
  if not platform.user_has_permission(target_workspace, 'subscriptions.manage') then
    return false;
  end if;
  select id into selected_plan from platform.plans
    where code=plan_code and status='active';
  if selected_plan is null then return false; end if;
  update platform.workspace_subscriptions set plan_id=selected_plan,
    state=new_state, updated_at=now() where workspace_id=target_workspace;
  return found;
end $$;

-- Function hardening: no implicit PUBLIC API, fixed empty search_path above.
revoke all on function platform.stage7c_seed_defaults() from public;
revoke all on function platform.stage7c_entitlement_decision(uuid,text,bigint) from public;
revoke all on function platform.check_workspace_entitlement(uuid,text,bigint) from public;
revoke all on function platform.resolve_entitlement(uuid,text) from public;
revoke all on function platform.stage7c_enforce_count_limit() from public;
revoke all on function platform.check_invitation_creation(uuid,timestamptz) from public;
revoke all on function platform.stage7c_enforce_invitation_policy() from public;
revoke all on function platform.accept_invitation_stage7c(text,text) from public;
revoke all on function platform.accept_invitation(text,text) from public;
revoke all on function platform.check_api_key_creation(uuid) from public;
revoke all on function platform.create_workspace_api_key(uuid,text,text,text,text,text[],timestamptz) from public;
revoke all on function platform.revoke_workspace_api_key(uuid,uuid) from public;
revoke all on function platform.lookup_workspace_api_key(text) from public;
revoke all on function platform.touch_workspace_api_key(uuid) from public;
revoke all on function platform.update_workspace_provider(uuid,text,boolean,text,text) from public;
revoke all on function platform.save_credential_reference(uuid,text,text,text,text) from public;
revoke all on function platform.delete_credential_reference(uuid,uuid) from public;
revoke all on function platform.update_workspace_security(uuid,boolean,boolean,integer) from public;
revoke all on function platform.update_workspace_settings(uuid,text,text,text,text) from public;
revoke all on function platform.update_workspace_subscription(uuid,text,text) from public;

grant execute on function platform.check_workspace_entitlement(uuid,text,bigint)
  to knowledge_platform_runtime;
grant execute on function platform.resolve_entitlement(uuid,text)
  to knowledge_platform_runtime;
grant execute on function platform.check_invitation_creation(uuid,timestamptz)
  to knowledge_platform_runtime;
grant execute on function platform.accept_invitation_stage7c(text,text)
  to knowledge_platform_runtime;
grant execute on function platform.accept_invitation(text,text)
  to knowledge_platform_runtime;
grant execute on function platform.check_api_key_creation(uuid)
  to knowledge_platform_runtime;
grant execute on function platform.create_workspace_api_key(uuid,text,text,text,text,text[],timestamptz)
  to knowledge_platform_runtime;
grant execute on function platform.revoke_workspace_api_key(uuid,uuid)
  to knowledge_platform_runtime;
grant execute on function platform.lookup_workspace_api_key(text)
  to knowledge_platform_runtime;
grant execute on function platform.touch_workspace_api_key(uuid)
  to knowledge_platform_runtime;
grant execute on function platform.update_workspace_provider(uuid,text,boolean,text,text)
  to knowledge_platform_runtime;
grant execute on function platform.save_credential_reference(uuid,text,text,text,text)
  to knowledge_platform_runtime;
grant execute on function platform.delete_credential_reference(uuid,uuid)
  to knowledge_platform_runtime;
grant execute on function platform.update_workspace_security(uuid,boolean,boolean,integer)
  to knowledge_platform_runtime;
grant execute on function platform.update_workspace_settings(uuid,text,text,text,text)
  to knowledge_platform_runtime;
grant execute on function platform.update_workspace_subscription(uuid,text,text)
  to knowledge_platform_runtime;

alter table platform.plans enable row level security;
alter table platform.plans force row level security;
alter table platform.workspace_subscriptions enable row level security;
alter table platform.workspace_subscriptions force row level security;
alter table platform.plan_entitlements enable row level security;
alter table platform.plan_entitlements force row level security;
alter table platform.provider_registry enable row level security;
alter table platform.provider_registry force row level security;
alter table platform.workspace_provider_settings enable row level security;
alter table platform.workspace_provider_settings force row level security;
alter table platform.credential_references enable row level security;
alter table platform.credential_references force row level security;
alter table platform.workspace_api_keys enable row level security;
alter table platform.workspace_api_keys force row level security;
alter table platform.workspace_security_settings enable row level security;
alter table platform.workspace_security_settings force row level security;
alter table platform.workspace_settings enable row level security;
alter table platform.workspace_settings force row level security;

create policy plans_runtime_select on platform.plans
for select to knowledge_platform_runtime using (
  (select platform.user_has_permission(
    nullif(current_setting('app.workspace_id', true),'')::uuid, 'plans.read'
  ))
);
create policy subscriptions_runtime_select on platform.workspace_subscriptions
for select to knowledge_platform_runtime using (
  workspace_id = nullif(current_setting('app.workspace_id', true),'')::uuid
  and (select platform.user_has_permission(workspace_id, 'subscriptions.read'))
);
create policy entitlements_runtime_select on platform.plan_entitlements
for select to knowledge_platform_runtime using (
  (select platform.user_has_permission(
    nullif(current_setting('app.workspace_id', true),'')::uuid, 'subscriptions.read'
  ))
);
create policy providers_runtime_select on platform.provider_registry
for select to knowledge_platform_runtime using (
  (select platform.user_has_permission(
    nullif(current_setting('app.workspace_id', true),'')::uuid, 'providers.read'
  ))
);
create policy workspace_provider_settings_runtime_select
on platform.workspace_provider_settings for select to knowledge_platform_runtime using (
  workspace_id = nullif(current_setting('app.workspace_id', true),'')::uuid
  and (select platform.user_has_permission(workspace_id, 'providers.read'))
);
create policy credential_references_runtime_select
on platform.credential_references for select to knowledge_platform_runtime using (
  workspace_id = nullif(current_setting('app.workspace_id', true),'')::uuid
  and (select platform.user_has_permission(workspace_id, 'credentials.read'))
);
create policy workspace_api_keys_runtime_select
on platform.workspace_api_keys for select to knowledge_platform_runtime using (
  workspace_id = nullif(current_setting('app.workspace_id', true),'')::uuid
  and (select platform.user_has_permission(workspace_id, 'api_keys.read'))
);
create policy workspace_security_settings_runtime_select
on platform.workspace_security_settings for select to knowledge_platform_runtime using (
  workspace_id = nullif(current_setting('app.workspace_id', true),'')::uuid
  and (select platform.user_has_permission(workspace_id, 'security.read'))
);
create policy workspace_settings_runtime_select
on platform.workspace_settings for select to knowledge_platform_runtime using (
  workspace_id = nullif(current_setting('app.workspace_id', true),'')::uuid
  and (select platform.user_has_permission(workspace_id, 'settings.read'))
);

grant select on platform.plans, platform.plan_entitlements,
  platform.provider_registry to knowledge_platform_runtime;
grant select on platform.workspace_subscriptions,
  platform.workspace_provider_settings, platform.workspace_security_settings,
  platform.workspace_settings to knowledge_platform_runtime;
grant select (id,workspace_id,name,provider_code,status,updated_by,created_at,updated_at)
  on platform.credential_references to knowledge_platform_runtime;
grant select (id,workspace_id,name,key_prefix,scopes,created_by,created_at,
  last_used_at,expires_at,revoked_at)
  on platform.workspace_api_keys to knowledge_platform_runtime;

revoke all on platform.plans, platform.workspace_subscriptions,
  platform.plan_entitlements, platform.provider_registry,
  platform.workspace_provider_settings, platform.credential_references,
  platform.workspace_api_keys, platform.workspace_security_settings,
  platform.workspace_settings from anon, authenticated;
