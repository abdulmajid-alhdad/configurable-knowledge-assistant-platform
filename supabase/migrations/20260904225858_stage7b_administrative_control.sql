-- Stage 7B: workspace usage, enforceable governance, append-only audit,
-- recipient notifications, and truthful administrative operation history.
-- Forward-only: no product data is dropped or rewritten.

insert into platform.permissions (key, description) values
  ('usage.read', 'Read workspace usage metering'),
  ('governance.read', 'Read enforceable workspace governance'),
  ('governance.manage', 'Change enforceable workspace governance'),
  ('audit.read', 'Read workspace administrative audit history'),
  ('notifications.read', 'Read own workspace notifications'),
  ('notifications.manage', 'Create administrative notifications');

insert into platform.role_permissions (role_id, permission_key)
select role.id, permission.key
from platform.roles role
join platform.permissions permission on
  role.name in ('OWNER', 'ADMIN')
  and permission.key in (
    'usage.read', 'governance.read', 'governance.manage', 'audit.read',
    'notifications.read', 'notifications.manage'
  )
union all
select role.id, permission.key
from platform.roles role
join platform.permissions permission on
  role.name in ('MEMBER', 'VIEWER')
  and permission.key = 'notifications.read';

create table platform.usage_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces (id),
  actor_user_id uuid references auth.users (id),
  event_type text not null check (event_type ~ '^[a-z][a-z0-9_.]{2,79}$'),
  quantity numeric(20,4) not null default 1 check (quantity > 0),
  unit text not null check (unit ~ '^[a-z][a-z0-9_.]{0,39}$'),
  resource_type text,
  resource_id uuid,
  occurred_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object')
);
create index usage_events_workspace_time_idx
  on platform.usage_events (workspace_id, occurred_at desc);
create index usage_events_workspace_type_time_idx
  on platform.usage_events (workspace_id, event_type, occurred_at desc);

create table platform.governance_settings (
  workspace_id uuid not null references platform.workspaces (id) on delete cascade,
  setting_key text not null check (
    setting_key in ('assistant_creation_enabled', 'knowledge_processing_enabled')
  ),
  enabled boolean not null default true,
  updated_by uuid references auth.users (id),
  updated_at timestamptz not null default now(),
  primary key (workspace_id, setting_key)
);

create table platform.audit_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces (id),
  actor_user_id uuid references auth.users (id),
  action text not null check (action ~ '^[a-z][a-z0-9_.]{2,119}$'),
  resource_type text not null check (resource_type ~ '^[a-z][a-z0-9_.]{1,79}$'),
  resource_id uuid,
  outcome text not null check (outcome in ('succeeded', 'denied', 'failed')),
  request_id text,
  occurred_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object')
);
create index audit_events_workspace_time_idx
  on platform.audit_events (workspace_id, occurred_at desc, id);
create index audit_events_workspace_action_time_idx
  on platform.audit_events (workspace_id, action, occurred_at desc);
create index audit_events_workspace_actor_time_idx
  on platform.audit_events (workspace_id, actor_user_id, occurred_at desc);

create table platform.notifications (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces (id),
  recipient_user_id uuid not null references auth.users (id) on delete cascade,
  category text not null check (category ~ '^[a-z][a-z0-9_.]{2,79}$'),
  severity text not null default 'info' check (severity in ('info', 'warning', 'error')),
  title text not null check (char_length(title) between 1 and 160),
  message text not null check (char_length(message) between 1 and 500),
  resource_type text,
  resource_id uuid,
  created_at timestamptz not null default now(),
  read_at timestamptz,
  foreign key (workspace_id, recipient_user_id)
    references platform.workspace_memberships (workspace_id, user_id) on delete cascade
);
create index notifications_recipient_unread_idx
  on platform.notifications (workspace_id, recipient_user_id, created_at desc)
  where read_at is null;

create table platform.administrative_operations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references platform.workspaces (id),
  actor_user_id uuid references auth.users (id),
  operation_type text not null check (operation_type ~ '^[a-z][a-z0-9_.]{2,79}$'),
  status text not null check (status in ('succeeded', 'failed')),
  resource_type text,
  resource_id uuid,
  started_at timestamptz not null,
  completed_at timestamptz not null default now(),
  safe_error_category text,
  check (completed_at >= started_at),
  check (status = 'failed' or safe_error_category is null)
);
create index administrative_operations_workspace_time_idx
  on platform.administrative_operations (workspace_id, completed_at desc);

create function platform.stage7b_seed_governance()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into platform.governance_settings (workspace_id, setting_key, enabled)
  values
    (new.id, 'assistant_creation_enabled', true),
    (new.id, 'knowledge_processing_enabled', true);
  return new;
end $$;
create trigger stage7b_seed_governance_after_workspace
after insert on platform.workspaces
for each row execute function platform.stage7b_seed_governance();

create function platform.stage7b_audit_invitation_acceptance()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if old.status = 'pending' and new.status = 'accepted' then
    insert into platform.audit_events (
      workspace_id, actor_user_id, action, resource_type, resource_id,
      outcome, metadata
    ) values (
      new.workspace_id, new.accepted_by, 'invitation.accepted',
      'invitation', new.id, 'succeeded', '{}'::jsonb
    );
  end if;
  return new;
end $$;
create trigger stage7b_audit_invitation_acceptance_after_update
after update of status on platform.invitations
for each row execute function platform.stage7b_audit_invitation_acceptance();

insert into platform.governance_settings (workspace_id, setting_key, enabled)
select workspace.id, setting.setting_key, true
from platform.workspaces workspace
cross join (values ('assistant_creation_enabled'), ('knowledge_processing_enabled'))
  setting(setting_key);

create function platform.append_audit_event(
  target_workspace uuid, event_action text, event_resource_type text,
  event_resource_id uuid, event_outcome text, event_request_id text,
  event_metadata jsonb default '{}'::jsonb
) returns uuid language plpgsql security definer set search_path = '' as $$
declare event_id uuid;
begin
  if not platform.user_has_workspace_membership(target_workspace) then
    raise exception 'audit actor is not a workspace member';
  end if;
  insert into platform.audit_events (
    workspace_id, actor_user_id, action, resource_type, resource_id,
    outcome, request_id, metadata
  ) values (
    target_workspace, platform.current_user_id(), event_action,
    event_resource_type, event_resource_id, event_outcome,
    nullif(event_request_id, ''), coalesce(event_metadata, '{}'::jsonb)
  ) returning id into event_id;
  return event_id;
end $$;

create function platform.record_usage_event(
  target_workspace uuid, usage_type text, usage_quantity numeric,
  usage_unit text, usage_resource_type text, usage_resource_id uuid,
  usage_metadata jsonb default '{}'::jsonb
) returns uuid language plpgsql security definer set search_path = '' as $$
declare event_id uuid;
begin
  if not platform.user_has_workspace_membership(target_workspace) then
    raise exception 'usage actor is not a workspace member';
  end if;
  insert into platform.usage_events (
    workspace_id, actor_user_id, event_type, quantity, unit,
    resource_type, resource_id, metadata
  ) values (
    target_workspace, platform.current_user_id(), usage_type, usage_quantity,
    usage_unit, usage_resource_type, usage_resource_id,
    coalesce(usage_metadata, '{}'::jsonb)
  ) returning id into event_id;
  return event_id;
end $$;

create function platform.record_administrative_operation(
  target_workspace uuid, event_operation_type text, event_status text,
  event_resource_type text, event_resource_id uuid,
  event_started_at timestamptz, event_error_category text
) returns uuid language plpgsql security definer set search_path = '' as $$
declare operation_id uuid;
begin
  if not platform.user_has_workspace_membership(target_workspace) then
    raise exception 'operation actor is not a workspace member';
  end if;
  insert into platform.administrative_operations (
    workspace_id, actor_user_id, operation_type, status, resource_type,
    resource_id, started_at, safe_error_category
  ) values (
    target_workspace, platform.current_user_id(), event_operation_type,
    event_status, event_resource_type, event_resource_id, event_started_at,
    event_error_category
  ) returning id into operation_id;
  return operation_id;
end $$;

create function platform.enqueue_notification(
  target_workspace uuid, target_recipient uuid, event_category text,
  event_severity text, event_title text, event_message text,
  event_resource_type text, event_resource_id uuid
) returns uuid language plpgsql security definer set search_path = '' as $$
declare notification_id uuid;
begin
  if not platform.user_has_permission(target_workspace, 'notifications.manage') then
    raise exception 'notification management permission required';
  end if;
  if not exists (
    select 1 from platform.workspace_memberships membership
    where membership.workspace_id = target_workspace
      and membership.user_id = target_recipient
      and membership.status = 'active'
  ) then
    raise exception 'notification recipient is not an active workspace member';
  end if;
  insert into platform.notifications (
    workspace_id, recipient_user_id, category, severity, title, message,
    resource_type, resource_id
  ) values (
    target_workspace, target_recipient, event_category, event_severity,
    event_title, event_message, event_resource_type, event_resource_id
  ) returning id into notification_id;
  return notification_id;
end $$;

revoke all on function platform.stage7b_seed_governance() from public;
revoke all on function platform.stage7b_audit_invitation_acceptance() from public;
revoke all on function platform.append_audit_event(uuid,text,text,uuid,text,text,jsonb) from public;
revoke all on function platform.record_usage_event(uuid,text,numeric,text,text,uuid,jsonb) from public;
revoke all on function platform.record_administrative_operation(uuid,text,text,text,uuid,timestamptz,text) from public;
revoke all on function platform.enqueue_notification(uuid,uuid,text,text,text,text,text,uuid) from public;
grant execute on function platform.append_audit_event(uuid,text,text,uuid,text,text,jsonb)
  to knowledge_platform_runtime;
grant execute on function platform.record_usage_event(uuid,text,numeric,text,text,uuid,jsonb)
  to knowledge_platform_runtime;
grant execute on function platform.record_administrative_operation(uuid,text,text,text,uuid,timestamptz,text)
  to knowledge_platform_runtime;
grant execute on function platform.enqueue_notification(uuid,uuid,text,text,text,text,text,uuid)
  to knowledge_platform_runtime;

alter table platform.usage_events enable row level security;
alter table platform.usage_events force row level security;
alter table platform.governance_settings enable row level security;
alter table platform.governance_settings force row level security;
alter table platform.audit_events enable row level security;
alter table platform.audit_events force row level security;
alter table platform.notifications enable row level security;
alter table platform.notifications force row level security;
alter table platform.administrative_operations enable row level security;
alter table platform.administrative_operations force row level security;

create policy usage_events_runtime_select on platform.usage_events
for select to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and platform.user_has_permission(workspace_id, 'usage.read')
);
create policy governance_runtime_select on platform.governance_settings
for select to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and platform.user_has_workspace_membership(workspace_id)
);
create policy governance_runtime_update on platform.governance_settings
for update to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and platform.user_has_permission(workspace_id, 'governance.manage')
) with check (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and platform.user_has_permission(workspace_id, 'governance.manage')
);
create policy audit_events_runtime_select on platform.audit_events
for select to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and platform.user_has_permission(workspace_id, 'audit.read')
);
create policy notifications_runtime_select on platform.notifications
for select to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and recipient_user_id = platform.current_user_id()
  and platform.user_has_permission(workspace_id, 'notifications.read')
);
create policy notifications_runtime_update on platform.notifications
for update to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and recipient_user_id = platform.current_user_id()
  and platform.user_has_permission(workspace_id, 'notifications.read')
) with check (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and recipient_user_id = platform.current_user_id()
);
create policy administrative_operations_runtime_select
on platform.administrative_operations for select to knowledge_platform_runtime using (
  workspace_id = current_setting('app.workspace_id', true)::uuid
  and platform.user_has_permission(workspace_id, 'operations.read')
);

grant select on platform.usage_events, platform.audit_events,
  platform.administrative_operations to knowledge_platform_runtime;
grant select on platform.governance_settings, platform.notifications
  to knowledge_platform_runtime;
grant update (enabled, updated_by, updated_at)
  on platform.governance_settings to knowledge_platform_runtime;
grant update (read_at)
  on platform.notifications to knowledge_platform_runtime;
revoke all on platform.usage_events, platform.governance_settings,
  platform.audit_events, platform.notifications, platform.administrative_operations
  from anon, authenticated;
